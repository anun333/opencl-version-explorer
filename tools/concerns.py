#!/usr/bin/env python3
"""Derive the concerns each hypothetical-3.2 scenario raises, from stored results -> workbench/results/CONCERNS.md

Nothing here is opinion.  Each concern is produced by a stated rule over (a) test outcomes in
workbench/results/*.json, (b) data/model.json (extracted from the Khronos sources), and optionally
(c) one real device read with `clinfo --raw` on this machine.  Every line says which of those it
came from: TESTED, DERIVED (a rule over extracted data), SAMPLE (one device), or NOT KNOWABLE.
"""
import hashlib, json, os, re, subprocess, shutil, collections
from common import *

RES = os.path.join(ROOT, "workbench", "results")
M = json.load(open(os.path.join(DATA, "model.json")))
EXT = M["extensions"]
PLATFORM = re.compile(r"win32|d3d|dx9|dx_fence|egl|_gl_|android|dma_buf|opaque_fd|sync_fd|va_api")


def device_sample():
    """Real device facts from `clinfo --raw` (first device).  None if clinfo is unavailable."""
    if not shutil.which("clinfo"): return None
    out = subprocess.run(["clinfo", "--raw"], capture_output=True, text=True).stdout
    if not out: return None
    def val(name):
        m = re.search(r"CL_DEVICE_%s[ \t]+([^\n]*)$" % name, out, re.M)
        return m.group(1).strip() if m else ""
    exts = (val("EXTENSIONS") or "").split()
    return {"name": val("NAME"), "exts": set(exts),
            "svm": val("SVM_CAPABILITIES"), "gas": val("GENERIC_ADDRESS_SPACE_SUPPORT"), "pipes": val("PIPE_SUPPORT"),
            "enqueue": val("DEVICE_ENQUEUE_CAPABILITIES"), "nonuniform": val("NON_UNIFORM_WORK_GROUP_SUPPORT"),
            "collectives": val("WORK_GROUP_COLLECTIVE_FUNCTIONS_SUPPORT")}


def sample_has(dev, feature):
    """True / False / None (not mapped) for whether the sample device supports an optional feature."""
    if not dev: return None
    m = {"Shared Virtual Memory": lambda: bool(dev["svm"]), "Generic Address Space": lambda: dev["gas"] == "CL_TRUE",
         "Pipes": lambda: dev["pipes"] == "CL_TRUE", "Device-Side Enqueue": lambda: bool(dev["enqueue"]),
         "Non-Uniform Work-groups": lambda: dev["nonuniform"] == "CL_TRUE", "Work-group Collective Functions": lambda: dev["collectives"] == "CL_TRUE"}
    return m[feature]() if feature in m else None


def struct_count(r):
    p = os.path.join(ROOT, "workbench", "build", r["id"], "CL", "cl.h")
    if not os.path.exists(p): return None
    t = open(p).read()
    i = t.find("SYNTHETIC: hypothetical")
    return len(re.findall(r"typedef\s+struct\s*\w*\s*\{", t[i:])) if i >= 0 else 0


def concerns_for(r, dev):
    C = []   # (level, source, text)
    add = lambda lv, src, tx: C.append((lv, src, tx))
    ck = {c["id"]: c for c in r["checks"]}
    failed = [c["id"] for c in r["checks"] if c["pass"] is False]
    promos = [a["ext"] for a in r["asks"] if a["type"] == "promote"]
    if promos:
        P = [EXT[n] for n in promos if n in EXT]
        npass = sum(1 for c in r["checks"] if c["pass"] is True)
        add("info" if not failed else "high", "TESTED", "%d of %d checks pass on synthetic 3.2 headers%s" % (npass, npass + len(failed), "" if not failed else "; failing: " + ", ".join(failed)))
        names = r.get("synthetic", {})
        if names.get("commands"):
            n = names["commands"]; abi = ck.get("abi/icd-dispatch", {}).get("detail", [])
            add("notable" if n >= 10 else "info", "TESTED", "%d new commands: the ICD dispatch struct grows by %d bytes (%s); every ICD loader and driver must add these entries, and existing offsets are unchanged" % (n, 8 * n, (abi[1] if len(abi) > 1 else "")))
        sc = struct_count(r)
        if sc: add("info", "TESTED", "%d promoted struct type(s): core and extension structs become distinct types (tags renamed, as 3.1 did), so code passing one where the other is expected needs a cast or conversion" % sc)
        exp = [e["name"] for e in P if e["status"] == "experimental"]
        if exp: add("high", "DERIVED", "%d experimental extension(s) would be frozen into core: %s. The spec says of experimental extensions: \"features may be added, removed, or changed in non-backward compatible ways\" (appendix, Experimental Extensions)" % (len(exp), ", ".join(exp)))
        unr = [e["name"] for e in P if e["status"] == "unratified"]
        if unr: add("high", "DERIVED", "%d extension(s) without the registry's ratified attribute: %s" % (len(unr), ", ".join(unr)))
        plat = [e["name"] for e in P if PLATFORM.search(e["name"])]
        if plat: add("notable", "DERIVED", "%d platform-specific extension(s) (OS or graphics-API handle types): %s. Core would name handle types that only exist on some systems" % (len(plat), ", ".join(plat)))
        for f in r["rules"]["findings"]:
            if f["id"].endswith("/unmet-deps"): add("high", "DERIVED", f["text"])
        dep = sorted({d for e in P for d in e.get("dependents", []) if d not in promos})
        if dep: add("notable", "DERIVED", "%d other extension(s) depend on these and would need a core-version alternative in their `depends`: %s" % (len(dep), ", ".join(dep)))
        agg = collections.Counter()
        for e in P:
            for k, v in (e.get("mentions") or {}).items(): agg[k] += v
        top = [(k, v) for k, v in agg.most_common(4) if v >= 5 and k not in ("Images", "fp64 / int64 / fp16")]
        byname = sorted({f for e in P for k_, f in (("svm", "Shared Virtual Memory"), ("subgroup", "Sub-groups"), ("atomic", "Atomics / memory model"), ("image", "Images")) if k_ in e["name"]})
        if byname: add("notable", "DERIVED", "by name these extensions belong to optional-feature areas: %s. Check how each behaves on devices without the corresponding optional feature" % ", ".join(byname))
        if top: add("notable", "HEURISTIC", "spec text leans on optional features (keyword counts): %s. A promotion has to say what happens on devices lacking them" % ", ".join("%s %d" % t for t in top))
        words = sum(e.get("words") or 0 for e in P)
        add("notable" if words > 5000 else "info", "DERIVED", "%d words of extension spec text to merge into the API, C and SPIR-V specs; 3.0.19 to 3.1.0 touched %d API-spec files and %d extension files (many editorial)" % (words, M["touch"]["churn"]["API spec"]["files"], M["touch"]["churn"]["extension specs"]["files"]))
        if not names.get("commands") and not names.get("enums"):
            add("notable", "NOT KNOWABLE", "language-only: no header change, so the real cost is OpenCL C compiler, built-in and SPIR-V work; the sources cannot measure it")
        add("info", "DERIVED", "3.1 requires devices to keep reporting promoted extension names; expect the same obligation for these %d name(s)" % len(promos))
        if dev:
            have = [n for n in promos if n in dev["exts"]]
            add("info", "SAMPLE", "one real device (%s) already reports %d of these %d extensions%s" % ((dev["name"] or "").split(" (")[0], len(have), len(promos), ": " + ", ".join(have) if have else ""))
    for q in r["rules"].get("require", []):
        f = next(x for x in M["optional"] if x["title"] == q["feature"])
        add("notable", "DERIVED", "%s: %d appendix-H behaviours become dead branches for new-version devices, %d OpenCL C macro(s) and %d query(ies) become constant" % (q["feature"], q["rows"], len(q["macros"]), len(q["queries"])))
        has = sample_has(dev, q["feature"])
        if has is not None:
            extra = " (reports %s)" % dev["svm"] if q["feature"] == "Shared Virtual Memory" else ""
            add("high" if not has else "info", "SAMPLE", "the sample device (%s) %s %s today%s" % ((dev["name"] or "").split(" (")[0], "supports" if has else "does NOT support", q["feature"], extra))
    for f in r["rules"]["findings"]:
        if f["id"].endswith(("/implies",)): add("high", "DERIVED", f["text"])
        if f["id"].endswith(("/enables", "never-removed")) or "/where" in f["id"]: add("info", "DERIVED", f["text"])
    if any(a["type"] == "require" for a in r["asks"]):
        add("notable", "NOT KNOWABLE", "how many shipping devices and drivers would lose the ability to claim the new version; conformance-test cost; vendor appetite")
    if promos and not failed: add("info", "NOT KNOWABLE", "conformance-test coverage, driver and loader implementation effort, and working-group intent are outside the sources")
    return C


def main():
    dev = device_sample()
    runs = []
    for fn in sorted(os.listdir(RES)):
        if fn[:2] in ("d0", "r0", "x0") and fn.endswith(".json"):
            r = json.load(open(os.path.join(RES, fn)))
            if "checks" in r: runs.append(r)
    assert runs, "no direction scenarios found; run workbench.py run first"
    order = {"high": 0, "notable": 1, "info": 2}
    L = ["# Directions for a hypothetical OpenCL 3.2 and the concerns each raises", "",
         "Generated by `tools/concerns.py` from stored test results and extracted Khronos data. **Nothing here is a Khronos plan or a prediction.** Tags: TESTED (a script compiled or checked it), DERIVED (a stated rule over extracted data), HEURISTIC (keyword counts; a pointer, not a verdict), SAMPLE (one real device read on this machine), NOT KNOWABLE (outside the sources). Levels are rule-based: *high* = a hard failure, an unfinished extension, or a forced requirement; *notable* = a large or cross-cutting effect; *info* = a fact worth knowing.", ""]
    if dev: L += ["Sample device: %s (rusticl). SVM capabilities `%s`, generic address space `%s`, pipes `%s`, device enqueue `%s`, non-uniform work-groups `%s`, work-group collectives `%s`." % (dev["name"], dev["svm"], dev["gas"], dev["pipes"], dev["enqueue"] or "(none)", dev["nonuniform"], dev["collectives"]), ""]
    # summary matrix
    L += ["## Summary", "", "| direction | kind | tested (pass/fail) | high | notable |", "|---|---|---|---|---|"]
    body = []
    for r in runs:
        C = sorted(concerns_for(r, dev), key=lambda c: order[c[0]])
        p = sum(1 for c in r["checks"] if c["pass"] is True); f = sum(1 for c in r["checks"] if c["pass"] is False)
        kind = "promote" if any(a["type"] == "promote" for a in r["asks"]) else "require" if any(a["type"] == "require" for a in r["asks"]) else "deprecate"
        L.append("| [%s](#%s) | %s | %s | %d | %d |" % (r["title"].replace("Direction: ", ""), r["id"], kind, "%d / %d" % (p, f) if (p + f) and kind == "promote" else "n/a", sum(1 for c in C if c[0] == "high"), sum(1 for c in C if c[0] == "notable")))
        body += ["", '<a id="%s"></a>' % r["id"], "## %s" % r["title"], "", "`%s` — %s" % (r["id"], r["intent"] or ""), ""]
        for lv, src, tx in C: body.append("- **%s** `%s` %s" % (lv, src, tx))
    open(os.path.join(RES, "CONCERNS.md"), "w").write("\n".join(L + body) + "\n")
    short = lambda t: (t or "").split(" (")[0]
    data = {"sample": ({"name": short(dev["name"]), "svm": dev["svm"], "generic_address_space": dev["gas"], "pipes": dev["pipes"],
                        "device_enqueue": dev["enqueue"] or "(none)", "non_uniform_work_groups": dev["nonuniform"], "work_group_collectives": dev["collectives"]} if dev else None),
            "directions": []}
    for r in runs:
        C = sorted(concerns_for(r, dev), key=lambda c: order[c[0]])
        kind = "promote" if any(a["type"] == "promote" for a in r["asks"]) else "require" if any(a["type"] == "require" for a in r["asks"]) else "deprecate"
        data["directions"].append({"id": r["id"], "title": r["title"].replace("Direction: ", ""), "intent": r["intent"], "kind": kind,
                                   "passed": sum(1 for c in r["checks"] if c["pass"] is True), "failed": sum(1 for c in r["checks"] if c["pass"] is False),
                                   "concerns": [{"id": "%s-%s" % (r["id"].split("-")[0], hashlib.sha1((r["id"] + "|" + c).encode()).hexdigest()[:8]), "level": a, "source": b, "text": c} for a, b, c in C]})
    json.dump(data, open(os.path.join(RES, "concerns.json"), "w"), indent=1)
    print("wrote workbench/results/CONCERNS.md for %d directions" % len(runs))
    for r in runs:
        C = concerns_for(r, dev)
        print("%-42s high=%d notable=%d info=%d" % (r["id"], sum(1 for c in C if c[0] == "high"), sum(1 for c in C if c[0] == "notable"), sum(1 for c in C if c[0] == "info")))


if __name__ == "__main__":
    main()
