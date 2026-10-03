#!/usr/bin/env python3
"""3.2 workbench back end: evaluate hypothetical asks, test them for real, document outcomes.

    python3 workbench.py run [scenario-id ...]     run scenarios (default: all in tools/scenarios/)
    python3 workbench.py proposal ID FILE|ref:BRANCH [--sheet S.json]   test a change to xml/cl.xml (patch file, or a branch in the cloned docs repo); a feature sheet adds the optional-feature contract checks
    python3 workbench.py wizard SPEC.json           build a patch and feature sheet from a proposal description, then run the full proposal test
    python3 workbench.py selftest                  prove the tester still catches the known-bad example proposals
    python3 workbench.py compare A B               diff two stored results
    python3 workbench.py calibrate                 replay the real 3.1 promotions through the same rules

Layers, strongest evidence first:
  COMPILE  synthetic CL_VERSION_3_2 headers are generated from the real headers (main) and compiled
           with gcc and g++ at every target version; leak, ABI and equality checks run for real.
  REGISTRY integrity checks over cl.xml data (collisions, dangling dependencies, enum value clashes).
  RULES    the same dependency/naming rules the viewer shows.
Nothing here is a Khronos artifact.  Synthetic headers live under workbench/build/ and say so.
"""
import json, os, re, subprocess, sys, shutil, datetime, itertools, collections, tempfile
import xml.etree.ElementTree as ET
from common import *

WB = os.path.join(ROOT, "workbench")
SCEN = os.path.join(ROOT, "tools", "scenarios")
RES = os.path.join(WB, "results")
BUILD = os.path.join(WB, "build")
HEADERS_REF = "main"
SUFFIX = re.compile(r"(_KHR|KHR|_EXT|EXT|_khr|_ext)$")


def strip(n):
    return SUFFIX.sub("", n)


def load_model():
    return json.load(open(os.path.join(DATA, "model.json")))


# ---------------------------------------------------------------- registry detail (params, values)
def registry_detail():
    root = ET.fromstring(show(DOCS, "v3.1.2", "xml/cl.xml"))
    cmds, enums, types, groups = {}, {}, set(), {}
    for c in root.iter("command"):
        p = c.find("proto")
        if p is None:
            continue
        ret = re.sub(r"\s+", " ", "".join(p.find("type").itertext()) + "".join(p.itertext()).split(p.findtext("name"))[0].replace(p.findtext("type") or "", "", 1)).strip() if False else None
        rt = re.sub(r"\s+", " ", ("".join(p.itertext()).replace(p.findtext("name"), "")).strip())
        params = [re.sub(r"\s+", " ", "".join(x.itertext()).strip()) for x in c.findall("param")]
        cmds[p.findtext("name")] = {"ret": rt, "params": params}
    for g in root.iter("enums"):
        for e in g.findall("enum"):
            v = e.get("value")
            if v is None and e.get("bitpos") is not None:
                v = "(1 << %s)" % e.get("bitpos")
            enums[e.get("name")] = {"value": v, "group": g.get("name"), "bitmask": g.get("type") == "bitmask"}
    for t in root.iter("type"):
        if t.get("category") or t.find("name") is not None:
            n = t.get("name") or t.findtext("name")
            if n:
                types.add(n)
    return {"cmds": cmds, "enums": enums, "types": types}


# ---------------------------------------------------------------- RULES layer
def rules_for(scn, M, R):
    out = {"promote": [], "require": [], "findings": []}
    EXT = M["extensions"]
    names = [a["ext"] for a in scn["asks"] if a["type"] == "promote"]
    core_names = {s["n"] for f in M["core"] for s in f["symbols"]}
    all_defined = set(R["enums"]) | set(R["cmds"]) | R["types"]
    for n in names:
        e = EXT.get(n)
        if not e or not e["present"]:
            out["findings"].append({"id": "%s/exists" % n, "level": "fail", "text": "%s is not in the latest registry" % n})
            continue
        deps = [d for d in e.get("depends_on", []) if not d.startswith("CL_VERSION")]
        unmet = [d for d in deps if d not in names and not EXT.get(d, {}).get("promotedto")]
        needed = [d for d in e.get("dependents", []) if d not in names]
        syms = [s for s in e.get("symbols", []) if s["k"] in ("command", "enum", "type") and not s["n"].startswith("CL/") and s["n"].startswith(("cl", "CL"))]
        newnames = {}
        for s in syms:
            nn = strip(s["n"])
            newnames.setdefault(nn, []).append(s["n"])
        clash = sorted(nn for nn, o in newnames.items() if nn in all_defined and nn not in o)
        dup = sorted(nn for nn, o in newnames.items() if len(o) > 1)
        out["promote"].append({"ext": n, "status": e["status"], "unmet_deps": unmet, "dependents_outside": needed,
                               "symbols": len(syms), "words": e.get("words"), "mentions": e.get("mentions", {}),
                               "name_clashes": clash, "name_dups": dup})
        out["findings"].append({"id": "%s/status" % n, "level": "warn" if e["status"] == "experimental" else "info",
                                "text": "status %s%s" % (e["status"], ", revision " + e["revision"] if e.get("revision") else "")})
        if unmet:
            out["findings"].append({"id": "%s/unmet-deps" % n, "level": "warn", "text": "core would depend on non-promoted extension(s): " + ", ".join(unmet)})
        if needed:
            out["findings"].append({"id": "%s/dependents" % n, "level": "info", "text": "extensions that would need a core-version alternative in `depends`: " + ", ".join(needed)})
        if clash:
            out["findings"].append({"id": "%s/name-clash" % n, "level": "fail", "text": "stripped names already defined elsewhere: " + ", ".join(clash)})
        if not syms:
            out["findings"].append({"id": "%s/no-symbols" % n, "level": "info", "text": "no API symbols (language-only extension); promotion is spec/OpenCL C text only"})
    # implication graph between optional features, read from appendix H prose ("... must also define the feature macro ...")
    imp = collections.defaultdict(set)
    macro_owner = {m: f["title"] for f in M["optional"] for m in f["macros"]}
    for f in M["optional"]:
        for a_, b_ in re.findall(r"define the feature macro (\w+) must also define the feature macro (\w+)", f["text"]):
            if a_ in macro_owner and b_ in macro_owner: imp[macro_owner[a_]].add(macro_owner[b_])
    for a in scn["asks"]:
        if a["type"] == "deprecate":
            core_syms = {s_["n"]: f_["version"] for f_ in M["core"] for s_ in f_["symbols"]}
            ext_users = collections.defaultdict(list)
            for en, e in M["extensions"].items():
                for s_ in e.get("symbols", []): ext_users[s_["n"]].append(en)
            hs = json.load(open(os.path.join(DATA, "headers.json")))["symbols"]
            rg = json.load(open(os.path.join(DATA, "registry.json")))["tags"][-1]
            rdep = [n for f_ in rg["features"].values() for n in f_["deprecated"] if n in rg["commands"]]
            kept = [n for n in rdep if n in hs and hs[n]["last"] == "main"]
            icd_txt = open(os.path.join(BUILD, "_base", "CL", "cl_icd.h")).read() if os.path.exists(os.path.join(BUILD, "_base", "CL", "cl_icd.h")) else ""
            in_icd = [n for n in rdep if re.search(r"\b%s\b" % n, icd_txt)]
            never = next((c["text"] for c in M["changes"] if "never be removed" in c["text"]), None)
            for sym in a["symbols"]:
                if sym not in core_syms:
                    out["findings"].append({"id": "deprecate/%s/exists" % sym, "level": "fail", "text": "%s is not a core symbol in the registry" % sym}); continue
                users = [x for x in ext_users.get(sym, [])]
                rows = [(f_["title"]) for f_ in M["optional"] for r_ in f_["rows"] if sym in r_["api"] or sym in r_["behaviour"]]
                out["findings"].append({"id": "deprecate/%s/where" % sym, "level": "info",
                                        "text": "%s (core since %s): named in %d appendix-H behaviour row(s)%s; used by extensions: %s" % (sym, core_syms[sym], len(rows), " [" + ", ".join(sorted(set(rows))) + "]" if rows else "", ", ".join(users) or "none")})
            out["findings"].append({"id": "deprecate/never-removed", "level": "info", "text": "deprecation is marking only: the spec states \"%s\". Of the %d commands the registry already marks deprecated, %d are still declared in the current headers and %d still have a slot in the ICD dispatch table" % (never, len(rdep), len(kept), len(in_icd))})
            out.setdefault("deprecate", []).extend(a["symbols"])
        if a["type"] == "require":
            f = next((x for x in M["optional"] if x["title"] == a["feature"]), None)
            if not f:
                out["findings"].append({"id": "require/%s/exists" % a["feature"], "level": "fail", "text": "no such optional feature in appendix H"}); continue
            out["require"].append({"feature": f["title"], "rows": len(f["rows"]), "macros": f["macros"], "queries": f["queries"]})
            # what this feature itself needs (transitively), and which optional features depend on it
            need, todo = set(), list(imp.get(f["title"], []))
            while todo:
                x = todo.pop()
                if x not in need: need.add(x); todo.extend(imp.get(x, []))
            rev = sorted(t for t, ds in imp.items() if f["title"] in ds)
            if need: out["findings"].append({"id": "require/%s/implies" % f["title"], "level": "warn", "text": "appendix H says a device with %s must also support: %s; requiring it therefore also requires those" % (f["title"], ", ".join(sorted(need)))})
            if rev: out["findings"].append({"id": "require/%s/enables" % f["title"], "level": "info", "text": "optional features that depend on %s and would become easier to require next: %s" % (f["title"], ", ".join(rev))})
            out["findings"].append({"id": "require/%s/rows" % f["title"], "level": "info",
                                    "text": "%d appendix-H behaviours become dead branches for new-version devices; %d feature macro(s), %d query(ies) become constant" % (len(f["rows"]), len(f["macros"]), len(f["queries"]))})
    return out


# ---------------------------------------------------------------- synthetic headers
def export_headers(dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    p = subprocess.run("git --git-dir=%s archive %s CL | tar -x -C %s" % (HDRS, HEADERS_REF, dst), shell=True, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def synth(scn, M, R, outdir):
    """Write a hypothetical 3.2 header set into outdir/CL.  Returns a manifest of what was generated."""
    export_headers(outdir)
    CL = os.path.join(outdir, "CL")
    rd = lambda f: open(os.path.join(CL, f)).read()
    wr = lambda f, t: open(os.path.join(CL, f), "w").write(t)
    ext_h = rd("cl_ext.h")
    EXT = M["extensions"]
    names = [a["ext"] for a in scn["asks"] if a["type"] == "promote"]
    mf = {"types": [], "enums": [], "commands": [], "warnings": []}
    tmap = {}
    syms = []
    for n in names:
        for s in EXT.get(n, {}).get("symbols", []):
            if s["n"].startswith(("cl", "CL")) and not s["n"].startswith("CL/"):
                syms.append(s)
    for s in syms:
        if s["k"] == "type" and s["n"].startswith("cl_"):
            tmap[s["n"]] = strip(s["n"])
    tagmap = dict(tmap); tagmap.update({"_" + k: "_" + v for k, v in tmap.items()})   # struct tags are renamed with their typedef (as 3.1 did)
    def rename(text):
        return re.sub(r"\b(" + "|".join(map(re.escape, sorted(tagmap, key=len, reverse=True))) + r")\b", lambda m: tagmap[m.group(1)], text) if tagmap else text
    block, fn_types, icd = [], [], []
    typedefs = {}
    for m in re.finditer(r"\btypedef\b", ext_h):
        i, depth = m.start(), 0
        while i < len(ext_h):
            ch = ext_h[i]
            depth += (ch == "{") - (ch == "}")
            if ch == ";" and depth == 0:
                break
            i += 1
        stmt = ext_h[m.start():i + 1]
        nm = re.search(r"(\w+)\s*;\s*$", stmt)
        if nm and "(" not in stmt.split("{")[0]:          # skip function-pointer typedefs (declared separately)
            typedefs.setdefault(nm.group(1), stmt)
    for s in syms:
        if s["k"] == "type" and s["n"].startswith("cl_"):
            stmt = typedefs.get(s["n"])
            if stmt:
                block.append(rename(stmt))
                mf["types"].append(tmap[s["n"]])
            else:
                mf["warnings"].append("could not find a typedef for %s in cl_ext.h; aliasing instead" % s["n"])
                block.append("typedef %s %s;" % (s["n"], tmap[s["n"]]))
                mf["types"].append(tmap[s["n"]])
    for s in syms:
        if s["k"] == "enum":
            d = R["enums"].get(s["n"])
            nn = strip(s["n"])
            if not d or d["value"] is None:
                mf["warnings"].append("enum %s has no value in the registry" % s["n"]); continue
            if nn == s["n"]:
                continue
            block.append("#define %-48s %s" % (nn, d["value"]))
            mf["enums"].append(nn)
    for s in syms:
        if s["k"] == "command":
            d = R["cmds"].get(s["n"])
            nn = strip(s["n"])
            if not d:
                mf["warnings"].append("command %s not found in registry" % s["n"]); continue
            ret = rename(d["ret"]); params = [rename(p) for p in d["params"]]
            proto = "extern CL_API_ENTRY %s CL_API_CALL\n%s(%s) CL_API_SUFFIX__VERSION_3_2;" % (ret, nn, ",\n    ".join(params) if params else "void")
            block.append("#if !defined(CL_NO_CORE_PROTOTYPES)\n" + proto + "\n#endif")
            fn_types.append("typedef %s CL_API_CALL %s_t(\n    %s) CL_API_SUFFIX__VERSION_3_2;\n\ntypedef %s_t *\n%s_fn CL_API_SUFFIX__VERSION_3_2;\n" % (ret, nn, ",\n    ".join(params) if params else "void", nn, nn))
            icd.append(nn)
            mf["commands"].append(nn)
    # cl.h: new block before the final extern "C" close
    cl = rd("cl.h")
    marker = cl.rindex("#ifdef __cplusplus\n}\n#endif")
    cl = cl[:marker] + "#ifdef CL_VERSION_3_2\n/* SYNTHETIC: hypothetical OpenCL 3.2 promotions (%s) */\n\n%s\n\n#endif /* CL_VERSION_3_2 */\n\n" % (scn["id"], "\n\n".join(block)) + cl[marker:]
    wr("cl.h", cl)
    # cl_platform.h
    pl = rd("cl_platform.h")
    pl = pl.replace("#define CL_API_SUFFIX__VERSION_3_1 CL_API_SUFFIX_COMMON\n", "#define CL_API_SUFFIX__VERSION_3_1 CL_API_SUFFIX_COMMON\n#define CL_API_SUFFIX__VERSION_3_2 CL_API_SUFFIX_COMMON\n")
    assert "VERSION_3_2" in pl
    wr("cl_platform.h", pl)
    # cl_version.h
    v = rd("cl_version.h")
    v = v.replace("CL_TARGET_OPENCL_VERSION != 310", "CL_TARGET_OPENCL_VERSION != 310 && \\\n    CL_TARGET_OPENCL_VERSION != 320")
    v = v.replace("#define CL_TARGET_OPENCL_VERSION 310", "#define CL_TARGET_OPENCL_VERSION 320")
    v = v.replace("#if CL_TARGET_OPENCL_VERSION >= 310 && !defined(CL_VERSION_3_1)", "#if CL_TARGET_OPENCL_VERSION >= 320 && !defined(CL_VERSION_3_2)\n#define CL_VERSION_3_2  1\n#endif\n#if CL_TARGET_OPENCL_VERSION >= 310 && !defined(CL_VERSION_3_1)")
    assert "CL_VERSION_3_2" in v and "!= 320" in v, "cl_version.h transform did not apply"
    wr("cl_version.h", v)
    if fn_types:
        ft = rd("cl_function_types.h")
        m = ft.rindex("#endif /* OPENCL_CL_FUNCTION_TYPES_H_ */")
        ft = ft[:m] + "#ifdef CL_VERSION_3_2\n\n" + "\n".join(fn_types) + "\n#endif /* CL_VERSION_3_2 */\n\n" + ft[m:]
        wr("cl_function_types.h", ft)
        ic = rd("cl_icd.h")
        entries = "\n  /* OpenCL 3.2 (SYNTHETIC) */\n" + "".join("#ifdef CL_VERSION_3_2\n  %s_t *%s;\n#else\n  void *%s;\n#endif\n" % (c, c, c) for c in icd)
        m = ic.rindex("} cl_icd_dispatch;")
        ic = ic[:m] + entries.lstrip("\n") + "\n" + ic[m:]
        wr("cl_icd.h", ic)
    open(os.path.join(outdir, "SYNTHETIC-NOT-A-KHRONOS-ARTIFACT.txt"), "w").write("Generated by tools/workbench.py for scenario %s from OpenCL-Headers %s.\n" % (scn["id"], HEADERS_REF))
    return mf


# ---------------------------------------------------------------- COMPILE layer
def sh(cmd, cwd=None, timeout=120):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def compile_checks(scn, mf, outdir, basedir):
    res = []
    targets = [100, 110, 120, 200, 210, 220, 300, 310, 320]
    flags = "-Wall -Wextra -Werror -Wno-deprecated-declarations -Wno-unused-parameter"
    inc = "-I%s" % outdir
    tdir = os.path.join(outdir, "t"); os.makedirs(tdir, exist_ok=True)
    open(os.path.join(tdir, "inc.c"), "w").write('#include <CL/cl.h>\n#include <CL/cl_ext.h>\n#include <CL/cl_icd.h>\n#include <CL/cl_function_types.h>\nint main(void){return 0;}\n')
    open(os.path.join(tdir, "inc.cpp"), "w").write(open(os.path.join(tdir, "inc.c")).read())
    # C1: every header combination compiles at every target (C99 and C++17)
    fails = []
    for t, (lang, std, cc) in itertools.product(targets, [("c", "c99", "gcc"), ("cpp", "c++17", "g++")]):
        for beta in ("", "-DCL_ENABLE_BETA_EXTENSIONS"):
            rc, out = sh("%s -std=%s %s %s -DCL_TARGET_OPENCL_VERSION=%d %s -c t/inc.%s -o /dev/null" % (cc, std, flags, inc, t, beta, lang), cwd=outdir)
            if rc:
                fails.append("%s %d %s: %s" % (lang, t, beta or "-", out.splitlines()[0] if out else "?"))
    res.append({"id": "compile/all-targets", "title": "headers compile at every target version (C99, C++17, with and without beta)", "pass": not fails,
                "detail": fails[:6] or ["%d compiles ok" % (len(targets) * 4)]})
    if not (mf["commands"] or mf["enums"] or mf["types"]):
        res.append({"id": "compile/new-symbols", "title": "new core symbols usable at target 320", "pass": None, "detail": ["scenario promotes no API symbols; nothing to compile"]})
        return res
    # C2: new symbols usable at 320 through <CL/cl.h> alone (no cl_ext.h): core must be self-sufficient
    use = ['#include <CL/cl.h>', "int main(void){ (void)0;"]
    for e in mf["enums"]: use.append("  { long v = (long)(%s); (void)v; }" % e)
    for c in mf["types"]: use.append("  { %s *p = 0; (void)p; }" % c)
    for f in mf["commands"]: use.append("  { void *p = (void*)&%s; (void)p; }" % f)
    use.append("  return 0; }")
    open(os.path.join(tdir, "use.c"), "w").write("\n".join(use))
    rc, out = sh("gcc -std=c99 %s %s -DCL_TARGET_OPENCL_VERSION=320 -c t/use.c -o /dev/null" % (flags, inc), cwd=outdir)
    res.append({"id": "compile/new-symbols", "title": "every new core symbol is usable at target 320 from <CL/cl.h> alone", "pass": rc == 0,
                "detail": ["%d enums, %d types, %d commands referenced" % (len(mf["enums"]), len(mf["types"]), len(mf["commands"]))] if rc == 0 else out.splitlines()[:6]})
    # C3: leak check — at 310 the same program MUST fail to compile
    rc, out = sh("gcc -std=c99 %s -DCL_TARGET_OPENCL_VERSION=310 -c t/use.c -o /dev/null" % inc, cwd=outdir)
    res.append({"id": "compile/no-leak-at-310", "title": "new symbols are NOT visible at target 310 (guard works)", "pass": rc != 0,
                "detail": ["compile failed as required: " + next((l.strip()[:150] for l in out.splitlines() if "error" in l), out[:100])] if rc else ["compiled, so the guard leaks"]})
    # C4: new enum values equal their KHR originals (needs cl_ext.h)
    asserts = ['#include <CL/cl.h>', '#include <CL/cl_ext.h>']
    pairs = []
    for s in [x for n in [a["ext"] for a in scn["asks"] if a["type"] == "promote"] for x in load_model()["extensions"][n].get("symbols", [])]:
        if s["k"] == "enum" and strip(s["n"]) in mf["enums"]:
            pairs.append((strip(s["n"]), s["n"]))
    asserts += ["_Static_assert((long)%s == (long)%s, \"%s\");" % (a, b, a) for a, b in pairs]
    asserts.append("int main(void){return 0;}")
    open(os.path.join(tdir, "eq.c"), "w").write("\n".join(asserts))
    rc, out = sh("gcc -std=c11 %s -DCL_TARGET_OPENCL_VERSION=320 -DCL_ENABLE_BETA_EXTENSIONS -c t/eq.c -o /dev/null" % inc, cwd=outdir)
    res.append({"id": "compile/enum-values-match", "title": "each core enum equals its extension original", "pass": rc == 0 if pairs else None,
                "detail": ["%d pairs equal" % len(pairs)] if rc == 0 and pairs else (out.splitlines()[:4] if pairs else ["no enums"])})
    # C5: ICD dispatch ABI — existing fields do not move; struct grows by exactly the new entries; same size at every target
    if mf["commands"]:
        base = open(os.path.join(basedir, "CL", "cl_icd.h")).read()
        m = re.search(r"typedef struct _cl_icd_dispatch \{(.*?)\} cl_icd_dispatch;", base, re.S)
        members = re.findall(r"\*\s*(cl[A-Za-z0-9_]+)\s*;|void \*(cl[A-Za-z0-9_]+);", m.group(1))
        members = sorted({a or b for a, b in members})
        prog = '#include <stddef.h>\n#include <stdio.h>\n#include <CL/cl_icd.h>\nint main(void){printf("size %zu\\n",sizeof(cl_icd_dispatch));\n' + "".join('printf("%s %%zu\\n",offsetof(cl_icd_dispatch,%s));\n' % (x, x) for x in members) + "return 0;}\n"
        outs = {}
        for label, d, t in (("base310", basedir, 310), ("syn310", outdir, 310), ("syn320", outdir, 320)):
            open(os.path.join(tdir, "abi_%s.c" % label), "w").write(prog)
            rc, o = sh("gcc -std=c99 -I%s -DCL_TARGET_OPENCL_VERSION=%d t/abi_%s.c -o t/abi_%s && t/abi_%s" % (d, t, label, label, label), cwd=outdir)
            outs[label] = o if rc == 0 else None
            if rc: res.append({"id": "abi/build-" + label, "title": "ABI probe builds (%s)" % label, "pass": False, "detail": o.splitlines()[:4]})
        if all(outs.values()):
            parse = lambda s: {l.split()[0]: int(l.split()[1]) for l in s.splitlines()}
            b, s310, s320 = parse(outs["base310"]), parse(outs["syn310"]), parse(outs["syn320"])
            moved = [k for k in b if k != "size" and b[k] != s320.get(k)]
            grew = s320["size"] - b["size"]
            want = 8 * len(mf["commands"])
            ok = not moved and grew == want and s310 == s320
            res.append({"id": "abi/icd-dispatch", "title": "cl_icd_dispatch: existing offsets unchanged, grows by one pointer per new command, same layout at 310 and 320", "pass": ok,
                        "detail": ["%d existing fields checked, none moved" % len(b) if not moved else "moved: %s" % moved[:5], "size %d -> %d (+%d bytes, expected +%d)" % (b["size"], s320["size"], grew, want),
                                   "layout identical at targets 310/320: %s" % (s310 == s320)]})
    return res


# ---------------------------------------------------------------- REGISTRY layer
def registry_checks(scn, M, R, mf):
    res = []
    names = [a["ext"] for a in scn["asks"] if a["type"] == "promote"]
    core_enum_val = collections.defaultdict(dict)
    promoted = set()
    for n in names:
        for s in M["extensions"].get(n, {}).get("symbols", []):
            promoted.add(s["n"])
    for f in M["core"]:
        for s in f["symbols"]:
            if s["k"] == "enum" and R["enums"].get(s["n"], {}).get("value"):
                core_enum_val[R["enums"][s["n"]]["group"]][R["enums"][s["n"]]["value"].lower()] = s["n"]
    clashes = []
    for n in names:
        for s in M["extensions"].get(n, {}).get("symbols", []):
            d = R["enums"].get(s["n"]) if s["k"] == "enum" else None
            if d and d["value"]:
                other = core_enum_val.get(d["group"], {}).get(d["value"].lower())
                if other and other != strip(s["n"]):
                    clashes.append("%s=%s in group %s already used by core %s" % (s["n"], d["value"], d["group"], other))
    res.append({"id": "registry/enum-value-clash", "title": "promoted enum values do not collide with existing core values in the same group", "pass": not clashes, "detail": clashes[:6] or ["no collisions"]})
    # dangling: promoted commands/types referencing types defined only in non-promoted extensions
    dang = []
    ext_types = collections.defaultdict(set)
    for en, e in M["extensions"].items():
        for s in e.get("symbols", []):
            if s["k"] == "type" and s["n"].startswith("cl_"):
                ext_types[s["n"]].add(en)
    for n in names:
        for s in M["extensions"].get(n, {}).get("symbols", []):
            if s["k"] == "command" and s["n"] in R["cmds"]:
                for p in [R["cmds"][s["n"]]["ret"]] + R["cmds"][s["n"]]["params"]:
                    for t in re.findall(r"\bcl_[a-z0-9_]+\b", p):
                        owners = ext_types.get(t)
                        if owners and not (owners & set(names)):
                            dang.append("%s uses %s defined only by %s" % (s["n"], t, ", ".join(sorted(owners))))
    res.append({"id": "registry/dangling-types", "title": "promoted commands only use core types or types promoted with them", "pass": not dang, "detail": sorted(set(dang))[:6] or ["none"]})
    return res


# ---------------------------------------------------------------- calibration: replay real 3.1
def calibrate(M, R):
    actual = {s["n"]: s for s in next(f for f in M["core"] if f["version"] == "3.1")["symbols"]}
    prom = M["promoted_3_1"]
    predicted = set()
    for n in prom:
        for s in M["extensions"][n].get("symbols", []):
            if s["k"] in ("command", "enum", "type") and s["n"].startswith(("cl", "CL")) and not s["n"].startswith("CL/"):
                predicted.add(strip(s["n"]))
    a = set(actual)
    # the 3.1 block also carries symbols that did not come from the nine promotions (e.g. CL_DEVICE_MAX_WORK_GROUP_SIZES)
    hit = predicted & a
    return {"promoted": prom, "predicted": len(predicted), "actual_in_3_1_feature": len(a), "correct": len(hit),
            "predicted_but_not_in_3_1": sorted(predicted - a), "in_3_1_but_not_predicted": sorted(a - predicted)}



# ---------------------------------------------------------------- PROPOSAL layer (a change to cl.xml, tested with Khronos's own generator)
def reg_index(xml_text):
    root = ET.fromstring(xml_text)
    d = {"enum_defs": collections.defaultdict(list), "cmd_defs": collections.defaultdict(list), "type_defs": set(), "groups": {}, "ext": {}, "feat": {}, "unresolved": set(), "cmds": {}}
    d["blocks"] = []
    for g in root.iter("enums"):
        for e in g.findall("enum"):
            d["enum_defs"][e.get("name")].append((g.get("name"), e.get("value") or ("bit%s" % e.get("bitpos"))))
            if g.get("start") and g.get("end") and e.get("value", "").lower().startswith("0x"):
                d["blocks"].append((g.get("name"), g.get("vendor"), int(g.get("start"), 16), int(g.get("end"), 16), e.get("name"), int(e.get("value"), 16)))
    for c in root.iter("command"):
        pr = c.find("proto")
        if pr is not None:
            d["cmd_defs"][pr.findtext("name")].append(1)
            d["cmds"][pr.findtext("name")] = {"ret": re.sub(r"\s+", " ", "".join(pr.itertext()).replace(pr.findtext("name"), "")).strip(),
                                              "params": [re.sub(r"\s+", " ", "".join(x.itertext()).strip()) for x in c.findall("param")]}
    d["struct_uses"] = {}
    for t in root.iter("type"):
        n = t.get("name") or t.findtext("name")
        if n: d["type_defs"].add(n)
        if t.get("category") == "struct" and t.get("name"):
            d["struct_uses"][t.get("name")] = [m_.text for mem in t.findall("member") for m_ in mem.findall("type") if m_.text]
    def reqs(el):
        out = []
        for rq in el.findall("require"):
            for ch in rq:
                if ch.tag in ("enum", "command", "type") and ch.get("name"):
                    out.append((ch.tag, ch.get("name")))
        return out
    for f in root.iter("feature"):
        d["feat"][f.get("name")] = reqs(f)
    for e in root.iter("extension"):
        d["ext"][e.get("name")] = {"depends": e.get("depends") or "", "experimental": e.get("experimental") == "true", "condition": e.get("condition") or "",
                                   "promotedto": e.get("promotedto") or "", "reqs": reqs(e), "revision": e.get("revision")}
    defs = {"enum": d["enum_defs"], "command": d["cmd_defs"]}
    for owner in list(d["feat"].items()) + [(k, v["reqs"]) for k, v in d["ext"].items()]:
        for kind, name in owner[1]:
            ok = (name in d["enum_defs"]) if kind == "enum" else (name in d["cmd_defs"]) if kind == "command" else (name in d["type_defs"])
            if not ok: d["unresolved"].add((owner[0], kind, name))
    return d


def vminor(dep):
    m = re.search(r"CL_VERSION_(\d)_(\d)", dep or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def gen_headers_from(xml_text, outdir, genroot):
    os.makedirs(outdir, exist_ok=True)
    xp = os.path.join(outdir, "cl.xml"); open(xp, "w").write(xml_text)
    gdir = os.path.join(outdir, "gen"); os.makedirs(gdir, exist_ok=True)
    rc, o = sh("python3 gen_headers.py -registry %s -o %s" % (xp, gdir), cwd=os.path.join(genroot, "scripts"), timeout=180)
    return rc, o, gdir


def run_proposal(pid, source, title=None, sheet=None):
    M = load_model()
    docs_commit = M["provenance"]["docs"]["v3.1.2"]["commit"]
    if source.startswith("ref:"):
        ref = source[4:]
        mb = git(DOCS, "merge-base", "main", ref).strip()
        base_xml = show(DOCS, "main", "xml/cl.xml"); old_xml = show(DOCS, mb, "xml/cl.xml"); theirs = show(DOCS, ref, "xml/cl.xml")
        assert base_xml and old_xml and theirs, "xml/cl.xml missing at main, %s or %s" % (mb[:8], ref)
        # apply only the branch's own change (merge-base -> ref) on top of current main, so a stale branch registry cannot mask or fake problems
        md = os.path.join(BUILD, "_merge", pid); os.makedirs(md, exist_ok=True)
        for n, t in (("ours.xml", base_xml), ("base.xml", old_xml), ("theirs.xml", theirs)): open(os.path.join(md, n), "w").write(t)
        rcm, merged = subprocess.run(["git", "merge-file", "-p", "ours.xml", "base.xml", "theirs.xml"], cwd=md, capture_output=True, text=True).returncode, None
        merged = subprocess.run(["git", "merge-file", "-p", "ours.xml", "base.xml", "theirs.xml"], cwd=md, capture_output=True, text=True).stdout
        union_note = None
        if rcm:
            merged = subprocess.run(["git", "merge-file", "-p", "--union", "ours.xml", "base.xml", "theirs.xml"], cwd=md, capture_output=True, text=True).stdout
            union_note = "%d conflict region(s) between the branch and current main were resolved by keeping both sides; additive registry edits usually merge this way, but the branch should be rebased by its author" % rcm
        prop_xml = merged
        origin = "the change on docs branch `%s` since its merge-base with main (`%s`, %s), merged onto current main" % (ref, mb[:8], git(DOCS, "log", "-1", "--format=%cs", mb).strip())
    elif source.startswith("xml:"):
        base_xml = show(DOCS, "v3.1.2", "xml/cl.xml"); prop_xml = open(source[4:]).read()
        origin = "a complete proposed registry built by the wizard from a proposal description, compared with the registry at v3.1.2"
    else:
        base_xml = show(DOCS, "v3.1.2", "xml/cl.xml")
        wd = os.path.join(BUILD, "_apply", pid); os.makedirs(os.path.join(wd, "xml"), exist_ok=True)
        open(os.path.join(wd, "xml", "cl.xml"), "w").write(base_xml)
        # GIT_CEILING_DIRECTORIES stops git from finding an enclosing repository: inside one, `git apply` silently skips paths and still exits 0
        _p = subprocess.run(["git", "apply", "--whitespace=nowarn", os.path.abspath(source)], cwd=wd, capture_output=True, text=True, env=dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(wd)))
        rc, o = _p.returncode, (_p.stdout + _p.stderr).strip()
        if rc:
            return {"id": pid, "title": title or pid, "intent": "", "asks": [{"type": "proposal", "patch": source}], "provenance": provenance(M),
                    "rules": {"findings": [{"id": "apply", "level": "fail", "text": "patch does not apply to xml/cl.xml at v3.1.2: " + o[:200]}]},
                    "checks": [{"id": "proposal/applies", "title": "patch applies cleanly to the registry", "pass": False, "detail": o.splitlines()[:4]}]}
        prop_xml = open(os.path.join(wd, "xml", "cl.xml")).read()
        if prop_xml == base_xml:
            return {"id": pid, "title": title or pid, "intent": "", "asks": [{"type": "proposal", "patch": source}], "provenance": provenance(M),
                    "rules": {"findings": [{"id": "apply", "level": "fail", "text": "the patch applied but changed nothing in xml/cl.xml (empty patch, or paths that do not match xml/cl.xml)"}]},
                    "checks": [{"id": "proposal/applies", "title": "patch changes the registry", "pass": False, "detail": ["the registry is identical after applying the patch"]}]}
        origin = "patch `%s` applied to the registry at v3.1.2" % os.path.basename(source)
    out = {"id": pid, "title": title or pid, "intent": "Proposal tested from " + origin + ". Hypothetical; not a Khronos artifact.", "asks": [{"type": "proposal", "patch": source}],
           "provenance": provenance(M), "rules": {"findings": []}, "checks": []}
    ck = out["checks"]; fnd = out["rules"]["findings"]
    if source.startswith("ref:") and union_note:
        fnd.append({"id": "merge-union", "level": "warn", "text": union_note})
    bdir = os.path.join(BUILD, "prop-" + pid)
    if os.path.exists(bdir): shutil.rmtree(bdir)
    os.makedirs(bdir)
    px = os.path.join(bdir, "proposed.xml"); open(px, "w").write(prop_xml)
    rc, o = sh("xmllint --noout %s" % px)
    ck.append({"id": "proposal/well-formed", "title": "proposed cl.xml is well-formed XML", "pass": rc == 0, "detail": o.splitlines()[:3] or ["ok"]})
    if rc: return out
    B, P = reg_index(base_xml), reg_index(prop_xml)
    new_enum = sorted(set(P["enum_defs"]) - set(B["enum_defs"])); new_cmd = sorted(set(P["cmd_defs"]) - set(B["cmd_defs"]))
    new_type = sorted(t for t in P["type_defs"] - B["type_defs"] if t.startswith("cl_"))
    new_ext = sorted(set(P["ext"]) - set(B["ext"])); chg_ext = sorted(n for n in set(P["ext"]) & set(B["ext"]) if P["ext"][n] != B["ext"][n])
    fnd.append({"id": "summary", "level": "info", "text": "adds %d enums, %d commands, %d types; %d new extensions, %d changed extensions" % (len(new_enum), len(new_cmd), len(new_type), len(new_ext), len(chg_ext))})
    # --- registry integrity (only problems the proposal introduces)
    dup = sorted(n for n, v in P["enum_defs"].items() if len(v) > 1 and len(B["enum_defs"].get(n, [])) <= 1) + sorted(n for n, v in P["cmd_defs"].items() if len(v) > 1 and len(B["cmd_defs"].get(n, [])) <= 1)
    ck.append({"id": "registry/no-duplicate-definitions", "title": "no symbol is defined twice", "pass": not dup, "detail": dup[:6] or ["none"]})
    unres = sorted(P["unresolved"] - B["unresolved"])
    ck.append({"id": "registry/references-resolve", "title": "every <require> names a defined type/enum/command", "pass": not unres, "detail": ["%s requires undefined %s %s" % u for u in unres[:6]] or ["none (baseline had %d pre-existing)" % len(B["unresolved"])]})
    byval = collections.defaultdict(list)
    for n, v in P["enum_defs"].items():
        for g, val in v: byval[(g, val)].append(n)
    bval = collections.defaultdict(list)
    for n, v in B["enum_defs"].items():
        for g, val in v: bval[(g, val)].append(n)
    clashes = ["%s and %s share value %s in %s" % (a[0], a[1], k[1], k[0]) for k, a in byval.items() if len(set(a)) > 1 and len(set(bval.get(k, []))) <= 1 and not k[1].startswith("bit")]
    ck.append({"id": "registry/no-enum-value-clash", "title": "new enum values do not collide within a group", "pass": not clashes, "detail": clashes[:6] or ["none"]})
    def order_problems(idx, names):
        out = []
        for n in names:
            lst = [nm for k, nm in idx["ext"][n]["reqs"] if k == "type"]
            for i, t in enumerate(lst):
                for mt in idx["struct_uses"].get(t, []):
                    if mt in lst and lst.index(mt) > i: out.append("%s lists structure %s before %s, which it uses" % (n, t, mt))
        return out
    badorder = sorted(set(order_problems(P, new_ext + chg_ext)) - set(order_problems(B, [n for n in new_ext + chg_ext if n in B["ext"]])))
    ck.append({"id": "registry/type-order", "title": "types in an extension's <require> list come after the types they use (the header generator emits them in this order)", "pass": not badorder,
               "detail": badorder[:6] + (["move the type it uses earlier in the <require> list"] if badorder else []) or ["none"]})
    allext = set(P["ext"]) | set(P["feat"])
    baddep = []
    for n in new_ext + chg_ext:
        for ident in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", P["ext"][n]["depends"]):
            if ident not in ("and", "or", "not") and ident not in allext: baddep.append("%s depends on unknown %s" % (n, ident))
    ck.append({"id": "registry/dependencies-resolve", "title": "extension `depends` name known extensions or core versions", "pass": not baddep, "detail": baddep[:6] or ["none"]})
    # naming convention (heuristic)
    badname = []
    for n in new_ext:
        m = re.match(r"cl_(khr|ext|[a-z0-9]+)_", n)
        sfx = {"khr": "KHR", "ext": "EXT"}.get(m.group(1), m.group(1).upper()) if m else None
        owned = [nm for k, nm in P["ext"][n]["reqs"] if k in ("enum", "command") and nm in (new_enum + new_cmd)]
        for nm in owned:
            if sfx and not re.search(r"(_%s|%s)$" % (sfx, sfx), nm): badname.append("%s: %s lacks the %s suffix" % (n, nm, sfx))
    fnd.append({"id": "naming", "level": "warn" if badname else "info", "text": ("suffix convention: " + "; ".join(badname[:4])) if badname else "new symbols follow the author-suffix convention (heuristic)"})
    bx = re.findall(r"<extension ([^>]*)>", base_xml)
    base_dep = len([e for e in bx if 'depends="CL_VERSION' in e]); base_nocond = len([e for e in bx if 'depends="CL_VERSION' in e and "condition=" not in e])
    # --- optional-feature contract (needs a feature sheet)
    if sheet:
        ock, ofn, draft = optional_contract(sheet, P, B, new_enum, new_cmd, new_ext, M)
        ck.extend(ock); fnd.extend(ofn); out["draft_appendix_h"] = draft
    else:
        fnd.append({"id": "optional/no-sheet", "level": "info", "text": "no feature sheet supplied, so the optional-feature contract (query, macro, behaviour when absent) was not checked"})
    # --- official generator: base vs proposed
    genroot = os.path.join(BUILD, "_hdr_src")
    if not os.path.exists(os.path.join(genroot, "scripts")):
        os.makedirs(genroot, exist_ok=True)
        assert sh("git --git-dir=%s archive %s scripts CL | tar -x -C %s" % (HDRS, HEADERS_REF, genroot))[0] == 0
    rc1, o1, g_base = gen_headers_from(base_xml, os.path.join(bdir, "base"), genroot)
    rc2, o2, g_prop = gen_headers_from(prop_xml, os.path.join(bdir, "prop"), genroot)
    ERRTXT = re.compile(r"Traceback|\b[A-Za-z]+Error:|: error in |Exception:")
    crashed2 = rc2 != 0 or bool(ERRTXT.search(o2)) or sorted(os.listdir(g_prop)) != sorted(os.listdir(g_base))
    ck.append({"id": "generator/runs", "title": "Khronos's header generator accepts the proposed registry (exit code, error text and output file set all checked: it can print an error yet exit 0)", "pass": not crashed2 and rc1 == 0 and not ERRTXT.search(o1),
               "detail": ([l.strip()[:160] for l in o2.splitlines() if l.strip()][-3:] if crashed2 else (o1.splitlines()[-3:] if rc1 else ["ok"]))})
    if rc1 or crashed2 or ERRTXT.search(o1): return out
    chg = {}
    for f in sorted(os.listdir(g_prop)):
        a = open(os.path.join(g_base, f)).read().splitlines() if os.path.exists(os.path.join(g_base, f)) else []
        b = open(os.path.join(g_prop, f)).read().splitlines()
        add = [l for l in b if l not in set(a)]; rem = [l for l in a if l not in set(b)]
        if add or rem: chg[f] = {"added": len(add), "removed": len(rem), "sample": [l.strip()[:110] for l in add if l.strip()][:6]}
    out["generated_diff"] = chg
    ck.append({"id": "generator/header-delta", "title": "generated headers change only where the proposal says (files changed: %s)" % (", ".join(chg) or "none"), "pass": bool(chg) or not (new_enum or new_cmd or new_type or new_ext),
               "detail": ["%s: +%d −%d lines" % (f, v["added"], v["removed"]) for f, v in chg.items()] or ["no generated header changed"]})
    # --- compile the proposed headers over the real core headers
    overlay = os.path.join(bdir, "inc"); export_headers(overlay)
    for f in os.listdir(g_prop): shutil.copy(os.path.join(g_prop, f), os.path.join(overlay, "CL", f))
    tdir = os.path.join(overlay, "t"); os.makedirs(tdir)
    open(os.path.join(tdir, "inc.c"), "w").write('#include <CL/cl.h>\n#include <CL/cl_ext.h>\n#include <CL/cl_icd.h>\n#include <CL/cl_function_types.h>\nint main(void){return 0;}\n')
    shutil.copy(os.path.join(tdir, "inc.c"), os.path.join(tdir, "inc.cpp"))
    flags = "-Wall -Wextra -Werror -Wno-deprecated-declarations -Wno-unused-parameter"
    fails = []
    for t, (lang, std, cc) in itertools.product([100, 110, 120, 200, 210, 220, 300, 310], [("c", "c99", "gcc"), ("cpp", "c++17", "g++")]):
        for beta in ("", "-DCL_ENABLE_BETA_EXTENSIONS"):
            rc, o = sh("%s -std=%s %s -I%s -DCL_TARGET_OPENCL_VERSION=%d %s -c t/inc.%s -o /dev/null" % (cc, std, flags, overlay, t, beta, lang), cwd=overlay)
            if rc: fails.append("%s %d %s: %s" % (lang, t, beta or "-", next((l.strip()[:150] for l in o.splitlines() if "error" in l), o[:100])))
    ck.append({"id": "compile/all-targets", "title": "proposed headers compile at every target version (C99, C++17, with and without beta)", "pass": not fails, "detail": fails[:5] or ["32 compiles ok"]})
    probe_names = [("enum", n) for n in new_enum if n in P["enum_defs"]] + [("cmd", n) for n in new_cmd] + [("type", n) for n in new_type]
    if probe_names:
        use = ["#include <CL/cl.h>", "#include <CL/cl_ext.h>", "int main(void){"]
        for k, n in probe_names:
            use.append({"enum": "  { long v = (long)(%s); (void)v; }", "cmd": "  { void *p = (void*)&%s; (void)p; }", "type": "  { %s *p = 0; (void)p; }"}[k] % n)
        use.append("  return 0; }")
        open(os.path.join(tdir, "use.c"), "w").write("\n".join(use))
        rc, o = sh("gcc -std=c99 %s -I%s -DCL_TARGET_OPENCL_VERSION=310 -DCL_ENABLE_BETA_EXTENSIONS -c t/use.c -o /dev/null" % (flags, overlay), cwd=overlay)
        ck.append({"id": "compile/new-symbols-usable", "title": "every new symbol is usable through <CL/cl_ext.h> (beta enabled)", "pass": rc == 0,
                   "detail": ["%d symbols referenced" % len(probe_names)] if rc == 0 else [l for l in o.splitlines() if "error" in l][:5]})
        # gating: below the extension's `depends` version, and without beta for experimental extensions, the symbols must not be visible
        gate = []
        for n in new_ext:
            e = P["ext"][n]; names = [(k, nm) for k, nm in e["reqs"] if (k == "enum" and nm in new_enum) or (k == "command" and nm in new_cmd)]
            if not names: continue
            k, nm = names[0]
            snippet = ["#include <CL/cl.h>", "#include <CL/cl_ext.h>", "int main(void){ " + ("long v=(long)(%s); (void)v;" % nm if k == "enum" else "void *p=(void*)&%s; (void)p;" % nm) + " return 0; }"]
            open(os.path.join(tdir, "gate.c"), "w").write("\n".join(snippet))
            mv = vminor(e["depends"])
            if mv:
                below = [t for t in (100, 110, 120, 200, 210, 220, 300, 310) if (t // 100, (t // 10) % 10) < mv]
                if below:
                    rc, _ = sh("gcc -std=c99 -I%s -DCL_TARGET_OPENCL_VERSION=%d -DCL_ENABLE_BETA_EXTENSIONS -c t/gate.c -o /dev/null" % (overlay, below[-1]), cwd=overlay)
                    hidden = rc != 0
                    if e["condition"]:
                        gate.append((n, "declares condition `%s`; hidden below OpenCL %d.%d (tested at %d)" % (e["condition"], mv[0], mv[1], below[-1]), hidden))
                    else:
                        gate.append((n, "no `condition` attribute, so %s below OpenCL %d.%d (tested at %d); %d of %d released extensions with a version dependency also omit it" % ("hidden" if hidden else "visible", mv[0], mv[1], below[-1], base_nocond, base_dep), True))
            if e["experimental"]:
                rc, _ = sh("gcc -std=c99 -I%s -DCL_TARGET_OPENCL_VERSION=310 -c t/gate.c -o /dev/null" % overlay, cwd=overlay)
                gate.append((n, "hidden without CL_ENABLE_BETA_EXTENSIONS (experimental)", rc != 0))
        if gate:
            ck.append({"id": "compile/gating", "title": "symbols are hidden where the registry says they should be", "pass": all(x[2] for x in gate), "detail": ["%s: %s: %s" % (n, w, "ok" if ok else "VISIBLE") for n, w, ok in gate][:6]})
    for c in ck: c["item"] = "%s::%s" % (pid, c["id"])
    for f in fnd: f["item"] = "%s::%s" % (pid, f["id"])
    out["unexpected"] = []
    out["synthetic"] = {"warnings": [], "names": {"types": new_type, "enums": new_enum, "commands": new_cmd}}
    return out



# ---------------------------------------------------------------- OPTIONAL-FEATURE CONTRACT (the 3.0 pairing: query + macro + behaviour when absent)
def existing_feature_macros():
    names = set()
    for f in ls_tree(DOCS, "v3.1.2"):
        if f.startswith(("c/", "api/appendix_h")) and f.endswith((".asciidoc", ".txt")):
            t = show(DOCS, "v3.1.2", f) or ""
            names |= set(re.findall(r"__opencl_c_[a-z0-9_]+", t))
            names |= {"__" + m for m in re.findall(r"\{(opencl_c_[a-z0-9_]+)\}", t)}
    return names


def optional_contract(sheet, P, B, new_enum, new_cmd, new_ext, M):
    """Checks a feature sheet against the proposed registry.  Returns (checks, findings, draft_markdown)."""
    ck, fnd = [], []
    ext_name = sheet.get("extension")
    ext = P["ext"].get(ext_name)
    ck.append({"id": "optional/extension-present", "title": "the sheet's extension exists in the proposed registry", "pass": ext is not None, "detail": [ext_name or "(no extension named)"]})
    if ext is None: return ck, fnd, ""
    req_enum = {n for k, n in ext["reqs"] if k == "enum"}; req_cmd = {n for k, n in ext["reqs"] if k == "command"}
    # 1. detection query
    qs = sheet.get("queries", [])
    bad = []
    for q in qs:
        if q not in P["enum_defs"]: bad.append("%s is not defined in the registry" % q); continue
        grp = {g for g, _ in P["enum_defs"][q]}
        if not any(g.endswith("_info") or g in ("cl_device_info", "cl_platform_info") for g in grp): bad.append("%s is in group %s, not an *_info query group" % (q, ",".join(sorted(grp))))
        if q not in req_enum: bad.append("%s is not required by %s" % (q, ext_name))
    if not qs: bad.append("no detection query declared (3.0 pairs every optional feature with a query)")
    ck.append({"id": "optional/query-declared", "title": "a detection query exists, is defined, and is required by the extension", "pass": not bad, "detail": bad[:6] or ["%d query(ies) ok" % len(qs)]})
    # 2. OpenCL C feature macro
    ms = sheet.get("macros", [])
    existing = existing_feature_macros()
    bad = []
    for m in ms:
        if not re.fullmatch(r"__opencl_c_[a-z0-9_]+", m): bad.append("%s does not match __opencl_c_<name>" % m)
        elif m in existing: bad.append("%s already exists in the specs" % m)
    ck.append({"id": "optional/macro-names", "title": "OpenCL C feature macros follow the naming pattern and do not collide with existing ones", "pass": not bad if ms else None,
               "detail": bad[:6] or (["%d macro(s) ok; %d existing macros checked" % (len(ms), len(existing))] if ms else ["no macro declared (fine for an API-only feature)"])})
    # 3. behaviour when absent, for every new command of the extension
    absent = sheet.get("absent", {})
    cmds = sorted(c for c in req_cmd if c in new_cmd)
    bad = [c + ": no behaviour-when-absent given" for c in cmds if c not in absent]
    bad += ["%s: %s is not a defined error code" % (c, e) for c, e in absent.items() if e not in P["enum_defs"]]
    bad += ["%s is not a command of %s" % (c, ext_name) for c in absent if c not in req_cmd]
    ck.append({"id": "optional/absent-behaviour", "title": "every new command says what it returns on a device that lacks the feature", "pass": not bad if cmds else None, "detail": bad[:6] or ["%d command(s) covered" % len(cmds)] if cmds else ["no new commands"]})
    # 4. precedent: how many appendix-H features follow the same pattern
    F = M["optional"]
    full = [f["title"] for f in F if f["macros"] and f["queries"] and f["rows"]]
    fnd.append({"id": "optional/precedent", "level": "info", "text": "pattern check: %d of %d appendix-H features have a query, a macro and behaviour rows; this sheet supplies query=%s macro=%s behaviour=%s" % (len(full), len(F), bool(qs), bool(ms), bool(absent))})
    # draft appendix-H section, in the existing format (a draft for the author, not spec text)
    L = ["== %s" % sheet.get("feature", ext_name), "", "%s is optional for devices supporting the new OpenCL version." % sheet.get("feature", ext_name), "When %s is not supported:" % sheet.get("feature", ext_name), "",
         '[cols="2,3",options="header",]', "|====", "|*API*", "|*Behavior*", ""]
    for q in qs: L += ["| {clGetDeviceInfo}, passing +", "{%s}" % q, "| May return `0` or an empty result, indicating that the feature is not supported.", ""]
    for c, e in sorted(absent.items()): L += ["| {%s}" % c, "| Returns {%s} if no devices in the context support the feature." % e, ""]
    L += ["|====", ""] + ["OpenCL C compilers supporting %s will define the feature macro {%s}." % (sheet.get("feature", ext_name), m.lstrip("_")) for m in ms]
    return ck, fnd, "\n".join(L)


def preflight():
    """Fail early and clearly: a missing compiler must not show up as 'the proposal failed to compile'."""
    missing = [t for t in ("gcc", "g++", "xmllint", "git", "tar") if not shutil.which(t)]
    try:
        import mako  # noqa: F401  (the official header generator needs it)
    except ImportError:
        missing.append("python3-mako")
    if missing:
        sys.exit("workbench needs: %s\nOn Debian/Ubuntu: sudo apt install build-essential libxml2-utils python3-mako git" % ", ".join(missing))


# ---------------------------------------------------------------- WIZARD: a declarative description of an extension -> patch + feature sheet -> full test
NAME_RE = {"extension": r"cl_[a-z0-9]+_[a-z0-9_]+", "enum": r"CL_[A-Z0-9_]+", "command": r"cl[A-Z][A-Za-z0-9_]+", "type": r"cl_[a-z0-9_]+", "macro": r"__opencl_c_[a-z0-9_]+"}
PARAM_RE = re.compile(r"^(const\s+)?([A-Za-z_]\w*)\s*(\*+)?\s*([A-Za-z_]\w*)$")
RET_RE = re.compile(r"^(const\s+)?([A-Za-z_]\w*)\s*(\*+)?$")


def order_types(types):
    """Scalars first, then structures so that a structure follows any structure of this proposal it uses. Returns (ordered, cyclic)."""
    scal = [t for t in types if "members" not in t]; st = [t for t in types if "members" in t]
    names = {t["name"] for t in st}
    uses = {t["name"]: {PARAM_RE.match(m.strip()).group(2) for m in t["members"] if m.strip() and PARAM_RE.match(m.strip())} & names for t in st}
    out, done = list(scal), set()
    todo = list(st)
    while todo:
        ready = [t for t in todo if uses[t["name"]] <= done]
        if not ready: return out + todo, True
        for t in ready: out.append(t); done.add(t["name"]); todo.remove(t)
    return out, False


def wizard_validate(spec, B):
    """Returns a list of plain-language problems with a proposal spec (empty list = fine to build)."""
    bad = []
    ext = spec.get("extension", {})
    if not re.fullmatch(NAME_RE["extension"], ext.get("name", "")): bad.append("extension name %r must look like cl_<author>_<name> (lower case)" % ext.get("name"))
    elif ext["name"] in B["ext"]: bad.append("extension %s already exists in the registry" % ext["name"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", ext.get("revision", "")): bad.append("revision %r must be major.minor.patch, for example 0.1.0 (the header generator requires it)" % ext.get("revision"))
    if ext.get("depends") and not re.fullmatch(r"[A-Za-z0-9_+,]+", ext["depends"]): bad.append("depends %r has unexpected characters" % ext["depends"])
    seen = set()
    if order_types(spec.get("types", []))[1]: bad.append("structures use each other in a circle; a structure can only use structures defined before it")
    for t in spec.get("types", []):
        if not re.fullmatch(NAME_RE["type"], t.get("name", "")): bad.append("type name %r must look like cl_<name>" % t.get("name"))
        if t.get("name") in B["type_defs"]: bad.append("type %s already exists in the registry" % t.get("name"))
        if "members" in t:
            ms = [m.strip() for m in t["members"] if m.strip()]
            if not ms: bad.append("structure %s needs at least one member" % t.get("name"))
            for m in ms:
                if not PARAM_RE.match(m): bad.append("structure %s: member %r must look like 'type name' or 'const type* name'" % (t.get("name"), m))
            mn = [PARAM_RE.match(m).group(4) for m in ms if PARAM_RE.match(m)]
            bad += ["structure %s: member name %s is used twice" % (t.get("name"), n) for n, k in collections.Counter(mn).items() if k > 1]
        elif t.get("base") not in ("cl_uint", "cl_bitfield", "cl_ulong", "cl_int", "cl_bool"):
            bad.append("type %s: base %r is not one of cl_uint, cl_bitfield, cl_ulong, cl_int, cl_bool (or give structure members)" % (t.get("name"), t.get("base")))
        seen.add(t.get("name"))
    for e in spec.get("enums", []):
        if not re.fullmatch(NAME_RE["enum"], e.get("name", "")): bad.append("enum name %r must be upper case starting CL_" % e.get("name"))
        if e.get("name") in B["enum_defs"]: bad.append("enum %s already exists in the registry" % e.get("name"))
        if not re.fullmatch(r"0x[0-9A-Fa-f]+|\d+|\(1 << \d+\)", str(e.get("value", ""))): bad.append("enum %s: value %r must be hex like 0x1234, a number, or (1 << n)" % (e.get("name"), e.get("value")))
        if not e.get("group"): bad.append("enum %s needs a group (for example cl_device_info)" % e.get("name"))
    for c in spec.get("commands", []):
        if not re.fullmatch(NAME_RE["command"], c.get("name", "")): bad.append("command name %r must look like clFooBar" % c.get("name"))
        if c.get("name") in B["cmd_defs"]: bad.append("command %s already exists in the registry" % c.get("name"))
        if not RET_RE.match(c.get("ret", "")): bad.append("command %s: return type %r not understood" % (c.get("name"), c.get("ret")))
        for p_ in c.get("params", []):
            if not PARAM_RE.match(p_.strip()): bad.append("command %s: parameter %r must look like 'type name' or 'const type* name'" % (c.get("name"), p_))
    names = [x.get("name") for k in ("types", "enums", "commands") for x in spec.get(k, [])]
    bad += ["%s is listed twice" % n for n, k in collections.Counter(names).items() if k > 1]
    return bad


def wizard_xml(spec, base_xml):
    ext = spec["extension"]; E = lambda t: t.replace("&", "&amp;").replace("<", "&lt;")
    def struct_xml(t):
        ms = ""
        for m_ in t["members"]:
            if not m_.strip(): continue
            m = PARAM_RE.match(m_.strip()); ms += "            <member>%s<type>%s</type>%s <name>%s</name></member>\n" % ("const " if m.group(1) else "", m.group(2), m.group(3) or "", m.group(4))
        return '        <type category="struct" name="%s">\n%s        </type>\n' % (t["name"], ms)
    spec = dict(spec, types=order_types(spec.get("types", []))[0])
    types = "".join(struct_xml(t) if "members" in t else '        <type category="define">typedef <type>%s</type>          <name>%s</name>;</type>\n' % (t["base"], t["name"]) for t in spec.get("types", []))
    groups = collections.OrderedDict()
    for e in spec.get("enums", []):
        v = str(e["value"]); vattr = ('bitpos="%s"' % re.search(r"\d+", v).group(0)) if v.startswith("(1 <<") else 'value="%s"' % v
        groups.setdefault((e["group"], e.get("vendor", "")), []).append((vattr, e["name"]))
    enums = "".join('    <enums name="%s"%s comment="Proposed in %s">\n%s    </enums>\n\n' % (g, (' vendor="%s"' % v) if v else "", spec.get("id", "proposal"), "".join('        <enum %s        name="%s"/>\n' % (va, n) for va, n in items)) for (g, v), items in groups.items())
    cmds = ""
    for c in spec.get("commands", []):
        rm = RET_RE.match(c["ret"]); ret = "%s<type>%s</type>%s" % ("const " if rm.group(1) else "", rm.group(2), rm.group(3) or "")
        ps = ""
        for p_ in c.get("params", []):
            m = PARAM_RE.match(p_.strip()); ps += "            <param>%s<type>%s</type>%s <name>%s</name></param>\n" % ("const " if m.group(1) else "", m.group(2), m.group(3) or "", m.group(4))
        cmds += "        <command>\n            <proto>%s <name>%s</name></proto>\n%s        </command>\n" % (ret, c["name"], ps)
    attrs = 'name="%s" revision="%s"' % (ext["name"], ext["revision"])
    if ext.get("depends"): attrs += ' depends="%s"' % ext["depends"]
    if ext.get("condition"): attrs += ' condition="%s"' % E(ext["condition"]).replace('"', "&quot;")
    if ext.get("experimental"): attrs += ' experimental="true"'
    req = ""
    if spec.get("types"): req += '            <require comment="Types">\n' + "".join('                <type name="%s"/>\n' % t["name"] for t in spec["types"]) + "            </require>\n"
    for (g, v), items in groups.items(): req += '            <require comment="%s">\n' % g + "".join('                <enum name="%s"/>\n' % n for _, n in items) + "            </require>\n"
    if spec.get("commands"): req += '            <require comment="Commands">\n' + "".join('                <command name="%s"/>\n' % c["name"] for c in spec["commands"]) + "            </require>\n"
    extx = '        <extension %s supported="opencl">\n%s        </extension>\n' % (attrs, req)
    x = base_xml
    if types:
        i = x.index('        <type category="define">typedef <type>'); x = x[:i] + types + x[i:]
    if enums:
        i = x.index("    <enums "); x = x[:i] + enums + x[i:]
    if cmds:
        i = x.index("    </commands>"); x = x[:i] + cmds + x[i:]
    i = x.index("    </extensions>"); x = x[:i] + extx + x[i:]
    return x


def wizard_sheet(spec):
    f = spec.get("feature")
    if not f: return None
    return {"feature": f.get("title", spec["extension"]["name"]), "extension": spec["extension"]["name"], "queries": f.get("queries", []), "macros": f.get("macros", []), "absent": f.get("absent", {})}


def run_wizard(spec):
    """Spec dict -> patch + sheet on disk -> full proposal test.  Returns the result dict."""
    M = load_model(); base = show(DOCS, "v3.1.2", "xml/cl.xml"); B = reg_index(base)
    pid = spec.get("id") or "wizard"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", pid): pid = "wizard"
    bad = wizard_validate(spec, B)
    if bad:
        return {"id": pid, "title": spec.get("title") or pid, "intent": "Built by the wizard from a proposal description.", "asks": [{"type": "proposal", "patch": "wizard:" + pid}], "provenance": provenance(M),
                "rules": {"findings": [{"id": "wizard/problem-%d" % i, "level": "fail", "text": t} for i, t in enumerate(bad)]},
                "checks": [{"id": "wizard/spec-valid", "title": "the proposal description is well-formed and its names are free", "pass": False, "detail": bad[:8]}]}
    prop = wizard_xml(spec, base)
    wd = os.path.join(WB, "proposals", pid); os.makedirs(wd, exist_ok=True)
    open(os.path.join(wd, "proposed.xml"), "w").write(prop)
    tmp = os.path.join(wd, "_diff"); os.makedirs(os.path.join(tmp, "a", "xml"), exist_ok=True); os.makedirs(os.path.join(tmp, "b", "xml"), exist_ok=True)
    open(os.path.join(tmp, "a", "xml", "cl.xml"), "w").write(base); open(os.path.join(tmp, "b", "xml", "cl.xml"), "w").write(prop)
    patch = subprocess.run(["git", "diff", "--no-index", "--no-color", "a/xml/cl.xml", "b/xml/cl.xml"], cwd=tmp, capture_output=True, text=True).stdout.replace("a/a/xml", "a/xml").replace("b/b/xml", "b/xml")
    open(os.path.join(wd, pid + ".patch"), "w").write(patch)
    sheet = wizard_sheet(spec)
    if sheet: json.dump(sheet, open(os.path.join(wd, pid + ".sheet.json"), "w"), indent=1)
    r = run_proposal(pid, "xml:" + os.path.join(wd, "proposed.xml"), spec.get("title"), sheet)
    r["wizard"] = {"patch": os.path.relpath(os.path.join(wd, pid + ".patch"), ROOT), "sheet": os.path.relpath(os.path.join(wd, pid + ".sheet.json"), ROOT) if sheet else None}
    return r


def save_result(r, pid=None):
    pid = pid or r["id"]
    os.makedirs(RES, exist_ok=True)
    for c in r["checks"]: c.setdefault("item", "%s::%s" % (pid, c["id"]))
    for f in r["rules"]["findings"]: f.setdefault("item", "%s::%s" % (pid, f["id"]))
    json.dump(r, open(os.path.join(RES, pid + ".json"), "w"), indent=1); open(os.path.join(RES, pid + ".md"), "w").write(write_md(r))
    with open(os.path.join(RES, "log.jsonl"), "a") as lg:
        lg.write(json.dumps({"when": r["provenance"]["when"], "id": pid, "checks": {c["id"]: c["pass"] for c in r["checks"]}, "docs": r["provenance"]["docs"]["commit"][:8], "headers": r["provenance"]["headers"]["commit"][:8]}) + "\n")


# ---------------------------------------------------------------- driver
def provenance(M):
    cc = sh("gcc --version | head -1")[1]
    return {"docs": {"tag": "v3.1.2", **M["provenance"]["docs"]["v3.1.2"]}, "headers": next(h for h in M["provenance"]["headers"] if h["ref"] == HEADERS_REF),
            "gcc": cc, "when": datetime.datetime.now().isoformat(timespec="seconds")}


def run_one(scn, M, R):
    out = {"id": scn["id"], "title": scn["title"], "intent": scn.get("intent", ""), "asks": scn["asks"], "provenance": provenance(M)}
    out["rules"] = rules_for(scn, M, R)
    bdir = os.path.join(BUILD, scn["id"]); base = os.path.join(BUILD, "_base")
    if not os.path.exists(os.path.join(base, "CL")):
        export_headers(base) if False else (os.makedirs(base, exist_ok=True), export_headers(base))
    mf = {"types": [], "enums": [], "commands": [], "warnings": []}
    if any(a["type"] == "promote" for a in scn["asks"]):
        mf = synth(scn, M, R, bdir)
        out["synthetic"] = {"dir": os.path.relpath(bdir, ROOT), **{k: (v if k == "warnings" else len(v)) for k, v in mf.items()}, "names": {k: mf[k] for k in ("types", "enums", "commands")}}
        out["checks"] = compile_checks(scn, mf, bdir, base) + registry_checks(scn, M, R, mf)
    else:
        out["checks"] = [{"id": "compile/none", "title": "no header change to test", "pass": None, "detail": ["scenario has no promotion; only rule findings apply"]}]
    clash_f = [f for f in out["rules"]["findings"] if f["id"].endswith("/name-clash")]
    out["checks"].append({"id": "rules/no-name-clash", "title": "stripped core names do not already exist anywhere in the registry", "pass": not clash_f,
                          "detail": [f["text"] for f in clash_f] or ["no clashes"]})
    # stable ids for every reportable line (so reactions can attach to them later)
    for f in out["rules"]["findings"]:
        f["item"] = "%s::%s" % (scn["id"], f["id"])
    for c in out["checks"]:
        c["item"] = "%s::%s" % (scn["id"], c["id"])
        if c["id"] in scn.get("expect", {}):
            c["expected"] = scn["expect"][c["id"]]
            c["as_expected"] = (c["pass"] == c["expected"])
    out["unexpected"] = [c["item"] for c in out["checks"] if c.get("as_expected") is False]
    return out


def write_md(r):
    L = ["# %s" % r["title"], "", "`%s` · %s" % (r["id"], r["provenance"]["when"]), ""]
    if r["intent"]: L += [r["intent"], ""]
    p = r["provenance"]
    L += ["Built from docs `%s` (%s) and headers `%s` (%s); %s. Synthetic headers are hypothetical and are not a Khronos artifact." % (p["docs"]["tag"], p["docs"]["commit"][:8], p["headers"]["ref"], p["headers"]["commit"][:8], p["gcc"]), ""]
    L += ["## Asks", ""] + ["- %s `%s`" % (a["type"], a.get("ext") or a.get("feature") or a.get("patch") or ", ".join(a.get("symbols", []))) for a in r["asks"]] + [""]
    L += ["## Tested (compile / ABI / registry)", ""]
    for c in r["checks"]:
        mark = {True: "PASS", False: "**FAIL**", None: "n/a"}[c["pass"]]
        note = "" if c.get("as_expected") is None else (" — expected %s, as expected" % ("pass" if c["expected"] else "fail") if c["as_expected"] else " — **UNEXPECTED: scenario expected %s**" % ("pass" if c["expected"] else "fail"))
        L += ["- %s — %s (`%s`)%s" % (mark, c["title"], c["item"], note)] + ["    - %s" % d for d in c["detail"]]
    L += ["", "## Rule findings (derived, not tested)", ""]
    for f in r["rules"]["findings"]:
        L.append("- [%s] %s (`%s`)" % (f["level"], f["text"], f["item"]))
    if r.get("generated_diff"):
        L += ["", "## What the official generator changes in the headers", ""]
        for f, v in r["generated_diff"].items():
            L += ["- `%s`: +%d / −%d lines" % (f, v["added"], v["removed"])] + ["    - `%s`" % x for x in v["sample"][:4]]
    if r.get("wizard"):
        L += ["", "## Files for you", "", "- patch to `xml/cl.xml` (suitable to share or attach to an issue): `%s`" % r["wizard"]["patch"]] + (["- feature sheet: `%s`" % r["wizard"]["sheet"]] if r["wizard"]["sheet"] else []) + [""]
    if r.get("draft_appendix_h"):
        L += ["", "## Draft appendix-H section (generated from the feature sheet; a starting point, not spec text)", "", "```asciidoc", r["draft_appendix_h"], "```"]
    if r.get("synthetic", {}).get("warnings"):
        L += ["", "## Generator warnings", ""] + ["- %s" % w for w in r["synthetic"]["warnings"]]
    L += ["", "## Not modelled", "", "- ICD loader implementation, CTS tests, spec prose, OpenCL C built-ins, implementations. The sources cannot say how costly these are.", ""]
    return "\n".join(L)


def cmd_run(ids):
    M = load_model(); R = registry_detail()
    files = sorted(f for f in os.listdir(SCEN) if f.endswith(".json"))
    scns = [json.load(open(os.path.join(SCEN, f))) for f in files]
    if ids: scns = [s for s in scns if s["id"] in ids]
    assert scns, "no scenarios matched"
    os.makedirs(RES, exist_ok=True)
    idx = []
    for s in scns:
        r = run_one(s, M, R)
        json.dump(r, open(os.path.join(RES, s["id"] + ".json"), "w"), indent=1)
        open(os.path.join(RES, s["id"] + ".md"), "w").write(write_md(r))
        with open(os.path.join(RES, "log.jsonl"), "a") as lg:
            lg.write(json.dumps({"when": r["provenance"]["when"], "id": s["id"], "checks": {c["id"]: c["pass"] for c in r["checks"]}, "docs": r["provenance"]["docs"]["commit"][:8], "headers": r["provenance"]["headers"]["commit"][:8]}) + "\n")
        if r["unexpected"]: print("  !! UNEXPECTED outcome(s):", r["unexpected"])
        print("%-34s %s" % (s["id"], " ".join("%s=%s" % (c["id"].split("/")[-1], {True: "ok", False: "FAIL", None: "-"}[c["pass"]]) for c in r["checks"])))
    # index of every stored result
    allr = [r for r in (json.load(open(os.path.join(RES, f))) for f in sorted(os.listdir(RES)) if f.endswith(".json") and not f.startswith(("calibration", "concerns"))) if "checks" in r]
    cols = []
    for r in allr:
        for c in r["checks"]:
            if c["id"] not in cols: cols.append(c["id"])
    I = ["# Scenario results", "", "| scenario | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for r in allr:
        m = {c["id"]: {True: "ok", False: "FAIL", None: "-"}[c["pass"]] for c in r["checks"]}
        I.append("| [%s](%s.md) | " % (r["id"], r["id"]) + " | ".join(m.get(c, "") for c in cols) + " |")
    open(os.path.join(RES, "INDEX.md"), "w").write("\n".join(I) + "\n")
    cal = calibrate(M, R)
    json.dump(cal, open(os.path.join(RES, "calibration-3.1.json"), "w"), indent=1)
    print("calibration (replay of real 3.1 promotions): predicted %d names, %d are in the real 3.1 feature block; extra in 3.1 not predicted: %s" % (cal["predicted"], cal["correct"], cal["in_3_1_but_not_predicted"][:4]))
    if cal["predicted_but_not_in_3_1"]:
        print("  predicted but absent from the 3.1 feature block:", cal["predicted_but_not_in_3_1"][:8])


def cmd_compare(a, b):
    ra, rb = (json.load(open(os.path.join(RES, x + ".json"))) for x in (a, b))
    ca, cb = ({c["id"]: c["pass"] for c in r["checks"]} for r in (ra, rb))
    print("checks:")
    for k in sorted(set(ca) | set(cb)):
        if ca.get(k) != cb.get(k): print("  %-32s %s -> %s" % (k, ca.get(k), cb.get(k)))
    na, nb = (set(sum((r.get("synthetic", {}).get("names", {}).get(k, []) for k in ("types", "enums", "commands")), [])) for r in (ra, rb))
    print("symbols only in %s: %d; only in %s: %d; shared %d" % (a, len(na - nb), b, len(nb - na), len(na & nb)))
    fa, fb = ({f["id"] for f in r["rules"]["findings"]} for r in (ra, rb))
    print("findings only in", a, sorted(fa - fb)[:8]); print("findings only in", b, sorted(fb - fa)[:8])


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    if sys.argv[1] in ("run", "proposal", "selftest", "wizard"): preflight()
    if sys.argv[1] == "run": cmd_run(sys.argv[2:])
    elif sys.argv[1] == "compare": cmd_compare(*sys.argv[2:4])
    elif sys.argv[1] == "proposal":
        argv = sys.argv[2:]; sheet = None
        if "--sheet" in argv:
            i = argv.index("--sheet"); sheet = json.load(open(argv[i + 1])); del argv[i:i + 2]
        pid, src = argv[0], argv[1]
        r = run_proposal(pid, src, " ".join(argv[2:]) or None, sheet)
        for c in r["checks"]: c.setdefault("item", "%s::%s" % (pid, c["id"]))
        for f in r["rules"]["findings"]: f.setdefault("item", "%s::%s" % (pid, f["id"]))
        os.makedirs(RES, exist_ok=True)
        json.dump(r, open(os.path.join(RES, pid + ".json"), "w"), indent=1); open(os.path.join(RES, pid + ".md"), "w").write(write_md(r))
        with open(os.path.join(RES, "log.jsonl"), "a") as lg:
            lg.write(json.dumps({"when": r["provenance"]["when"], "id": pid, "checks": {c["id"]: c["pass"] for c in r["checks"]}, "docs": r["provenance"]["docs"]["commit"][:8], "headers": r["provenance"]["headers"]["commit"][:8]}) + "\n")
        for c in r["checks"]: print("%-40s %s" % (c["id"], {True: "ok", False: "FAIL", None: "-"}[c["pass"]]), "|", "; ".join(c["detail"])[:140])
        print("report: workbench/results/%s.md" % pid)
    elif sys.argv[1] == "wizard":
        spec = json.load(open(sys.argv[2])); r = run_wizard(spec); save_result(r)
        for c in r["checks"]: print("%-40s %s" % (c["id"], {True: "ok", False: "FAIL", None: "-"}[c["pass"]]), "|", "; ".join(c["detail"])[:150])
        print("report: workbench/results/%s.md" % r["id"]); print("patch: %s" % (r.get("wizard") or {}).get("patch"))
    elif sys.argv[1] == "selftest":
        # each demo must fail exactly the checks listed (and the valid demo and the no-op control must fail none)
        EXPECT = {"example-ok": set(), "example-bad-dangling": {"registry/references-resolve", "generator/runs"}, "example-bad-range-clash": {"registry/no-enum-value-clash"},
                  "example-bad-gating": {"compile/gating"}, "example-bad-revision": {"generator/runs"},
                  "example-bad-type-order": {"registry/type-order", "compile/all-targets", "compile/new-symbols-usable"}}
        bad = []
        for name, want in EXPECT.items():
            r = run_proposal("self-" + name, os.path.join(ROOT, "tools", "proposals", name + ".patch"))
            got = {c["id"] for c in r["checks"] if c["pass"] is False}
            print("%-26s failed: %s" % (name, sorted(got) or "none"))
            if got != want: bad.append("%s: expected %s, got %s" % (name, sorted(want), sorted(got)))
        for label, sheetf, want in (("example-ok + good sheet", "example-ok.sheet.json", set()),
                                    ("example-ok + bad sheet", "example-bad.sheet.json", {"optional/query-declared", "optional/macro-names", "optional/absent-behaviour"})):
            r = run_proposal("self-sheet", os.path.join(ROOT, "tools", "proposals", "example-ok.patch"), None, json.load(open(os.path.join(ROOT, "tools", "proposals", sheetf))))
            got = {c["id"] for c in r["checks"] if c["pass"] is False}
            print("%-26s failed: %s" % (label, sorted(got) or "none"))
            if got != want: bad.append("%s: expected %s, got %s" % (label, sorted(want), sorted(got)))
        for name, want in (("example-wizard", set()), ("example-wizard-struct", set()), ("example-wizard-struct-order", set()), ("example-wizard-clash", {"wizard/spec-valid"}), ("example-wizard-incomplete", {"optional/macro-names", "optional/absent-behaviour"})):
            spec = json.load(open(os.path.join(ROOT, "tools", "proposals", name + ".json"))); spec["id"] = "self-" + name
            r = run_wizard(spec); got = {c["id"] for c in r["checks"] if c["pass"] is False}
            print("%-26s failed: %s" % ("wizard: " + name, sorted(got) or "none"))
            if got != want: bad.append("wizard %s: expected %s, got %s" % (name, sorted(want), sorted(got)))
            if name == "example-wizard" and not got:       # the patch it produced must itself apply and pass
                pf = os.path.join(ROOT, r["wizard"]["patch"]); rr = run_proposal("self-wizard-roundtrip", pf, None, wizard_sheet(spec))
                g2 = {c["id"] for c in rr["checks"] if c["pass"] is False}
                print("%-26s failed: %s" % ("wizard patch re-tested", sorted(g2) or "none"))
                if g2: bad.append("wizard patch round trip failed %s" % sorted(g2))
        # regression: a patch must apply even when the work folder sits inside a git repository (git apply silently skips paths there)
        probe = os.path.join(BUILD, "_gitrepo_probe"); os.makedirs(probe, exist_ok=True)
        subprocess.run(["git", "init", "-q", probe], check=True, capture_output=True)
        _saved = BUILD; BUILD = os.path.join(probe, "build")
        try:
            rr = run_proposal("self-apply-in-repo", os.path.join(ROOT, "tools", "proposals", "example-ok.patch"))
        finally:
            BUILD = _saved
        g3 = {c["id"] for c in rr["checks"] if c["pass"] is False}
        print("%-26s failed: %s" % ("patch applied inside a git repo", sorted(g3) or "none"))
        if g3 or not rr.get("synthetic", {}).get("names", {}).get("commands"): bad.append("a patch applied nothing when the work folder is inside a git repository (failed %s)" % sorted(g3))
        r = run_proposal("self-noop", "ref:main")
        got = {c["id"] for c in r["checks"] if c["pass"] is False}
        print("%-26s failed: %s" % ("control: main vs main", sorted(got) or "none"))
        if got: bad.append("no-op control failed %s" % sorted(got))
        sys.exit("SELFTEST FAIL:\n  " + "\n  ".join(bad)) if bad else print("selftest OK")
    elif sys.argv[1] == "calibrate": print(json.dumps(calibrate(load_model(), registry_detail()), indent=1))
    else: sys.exit(__doc__)
