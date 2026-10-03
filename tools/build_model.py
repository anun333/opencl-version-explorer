#!/usr/bin/env python3
"""Combine the extracted data files into data/model.json for the viewer.

Everything here is derived from data/*.json (which come from ../sources); nothing typed in.
Fields are labelled by provenance: extracted (read from a source file),
derived (computed from extracted data by a stated rule), heuristic (keyword match).
"""
import json, re, collections, sys
from common import *

L = lambda n: json.load(open(os.path.join(DATA, n)))


def vendor_class(name):
    m = re.match(r"cl_(khr|ext|[a-z0-9]+)_", name)
    p = m.group(1) if m else "?"
    return p if p in ("khr", "ext") else "vendor:" + p


OPT_KEYWORDS = collections.OrderedDict([
    ("Shared Virtual Memory", r"\bSVM\b|shared virtual memory"),
    ("Device-Side Enqueue", r"device[-_ ]side[-_ ]enqueue|device[-_ ]enqueue|on-device queue|enqueue_kernel"),
    ("Pipes", r"\bpipes?\b"),
    ("Generic Address Space", r"generic address space"),
    ("Program Scope Global Variables", r"program scope global|program-scope global"),
    ("Images", r"\bimages?\b|read_image|write_image"),
    ("Sub-groups", r"sub-?groups?"),
    ("Atomics / memory model", r"\batomic|memory consistency model|memory_order|memory_scope"),
    ("Work-group collectives", r"work_group_(?:reduce|scan|broadcast|all|any)|work-group collective"),
    ("Non-uniform work-groups", r"non-uniform work-group"),
    ("fp64 / int64 / fp16", r"\bdouble\b|\bfp64\b|\bfp16\b|\bhalf\b|\blong\b"),
    ("SPIR-V / IL", r"SPIR-V|intermediate language"),
])


def main():
    reg, struct, chg, opt, hdr, tp = (L(x) for x in ("registry.json", "structure.json", "changes.json", "optional.json", "headers.json", "touchpoints.json"))
    tags = reg["tags"]
    tnames = [t["tag"] for t in tags]
    last = tags[-1]
    cmds, egroup, evalue = last["commands"], last["enum_group"], last["enum_value"]

    # ---------------- core features (extracted from the 3.1.2 registry)
    core = []
    first_seen = {}
    for ver in sorted(last["features"], key=vkey):
        f = last["features"][ver]
        syms = []
        for s in f["symbols"]:
            n = s["name"]
            dep = f["deprecated"].get(n, "")
            syms.append({"n": n, "k": s["kind"], "g": s["group"] or egroup.get(n, ""), "dep": dep,
                         "v": evalue.get(n) or ""})
            first_seen.setdefault(n, ver)
        core.append({"version": ver, "name": f["name"], "symbols": syms})

    # ---------------- extensions: lifecycle across tags (extracted), status (derived)
    extnames = sorted({e for t in tags for e in t["extensions"]})
    extfiles = {e["name"]: e for e in struct["extfiles"]}
    changes_by_ext = collections.defaultdict(list)
    for i, c in enumerate(chg["entries"]):
        for e in c["exts"]:
            changes_by_ext[e].append(i)
    ext = {}
    for n in extnames:
        hist = []
        prev = None
        for t in tags:
            e = t["extensions"].get(n)
            snap = None if e is None else (e["revision"], e["ratified"], e["experimental"], e["promotedto"], e["obsoletedby"], len(e["symbols"]))
            if snap != prev:
                hist.append({"tag": t["tag"], "present": e is not None, "revision": e and e["revision"], "ratified": e and e["ratified"],
                             "experimental": e and e["experimental"], "promotedto": e and e["promotedto"], "obsoletedby": e and e["obsoletedby"],
                             "nsyms": e and len(e["symbols"])})
            prev = snap
        cur = last["extensions"].get(n)
        ext[n] = {"name": n, "class": vendor_class(n), "hist": hist, "first": hist[0]["tag"] if hist else None,
                  "present": cur is not None, "spec": extfiles.get(n), "changes": changes_by_ext.get(n, [])}
        if cur:
            ext[n].update({k: cur[k] for k in ("revision", "ratified", "experimental", "promotedto", "obsoletedby", "depends", "depends_on", "condition", "comment")})
            ext[n]["symbols"] = [{"n": s["name"], "k": s["kind"], "g": s["group"], "dep": s["depends"]} for s in cur["symbols"] if s["kind"] != "type" or not s["name"].startswith("CL/")]
    # reverse dependencies (derived)
    for n, e in ext.items():
        e["dependents"] = sorted(m for m, o in ext.items() if o.get("present") and n in (o.get("depends_on") or []))
    for n, e in ext.items():
        if not e["present"]:
            e["status"] = "removed"
        elif e.get("promotedto"):
            e["status"] = "promoted"
        elif e.get("obsoletedby"):
            e["status"] = "obsolete"
        elif e.get("experimental"):
            e["status"] = "experimental"
        elif e.get("ratified"):
            e["status"] = "ratified"
        else:
            e["status"] = "unratified"      # no ratified= attribute in the registry (includes vendor extensions)

    # ---------------- per-tag diffs between consecutive registry snapshots (extracted)
    diffs = []
    for a, b in zip(tags, tags[1:]):
        ea, eb = a["extensions"], b["extensions"]
        d = {"from": a["tag"], "to": b["tag"], "date": b["date"], "added": sorted(set(eb) - set(ea)), "removed": sorted(set(ea) - set(eb)),
             "changed": []}
        for n in sorted(set(ea) & set(eb)):
            x, y = ea[n], eb[n]
            what = []
            for k in ("revision", "ratified", "experimental", "promotedto", "obsoletedby", "depends"):
                if x[k] != y[k]:
                    what.append({"field": k, "from": x[k], "to": y[k]})
            sa = {s["name"] for s in x["symbols"]}; sb = {s["name"] for s in y["symbols"]}
            if sa != sb:
                what.append({"field": "symbols", "added": sorted(sb - sa), "removed": sorted(sa - sb)})
            if what:
                d["changed"].append({"ext": n, "what": what})
        fa, fb = a["features"], b["features"]
        d["features_added"] = sorted(set(fb) - set(fa))
        d["core_symbols_added"] = {v: sorted({s["name"] for s in fb[v]["symbols"]} - ({s["name"] for s in fa[v]["symbols"]} if v in fa else set())) for v in fb}
        d["core_symbols_added"] = {v: x for v, x in d["core_symbols_added"].items() if x}
        diffs.append(d)

    # ---------------- promotion precedent: what happened to the symbols of promoted extensions (derived)
    def strip(n):
        return re.sub(r"(_KHR|KHR|_EXT|EXT)$", "", n)
    core_names = {s["n"] for f in core for s in f["symbols"]}
    prec = []
    for n, e in ext.items():
        if e.get("promotedto") and e.get("symbols"):
            tgt = e["promotedto"].replace("CL_VERSION_", "").replace("_", ".")
            feat = {s["n"]: s for f in core if f["version"] == tgt for s in f["symbols"]}
            ss = [s for s in e["symbols"] if s["k"] in ("command", "enum")]
            same = [s["n"] for s in ss if s["n"] in feat]
            renamed = [(s["n"], strip(s["n"])) for s in ss if s["n"] not in feat and strip(s["n"]) in feat]
            prec.append({"ext": n, "to": tgt, "symbols": len(ss), "same_name_in_core": len(same), "renamed_in_core": renamed[:6],
                         "n_renamed": len(renamed)})
    # names the spec says promoted extensions must still report (extracted text)
    pl = show(DOCS, "v3.1.2", "api/opencl_platform_layer.asciidoc")
    m = re.search(r"must be returned by all devices that\s+support OpenCL 3\.1 or newer:\n\n((?:\{[a-z0-9_]+_EXT\}[ +]*\n)+)", pl)
    must_report = sorted(re.sub(r"_EXT$", "", x) for x in re.findall(r"\{([a-z0-9_]+_EXT)\}", m.group(1))) if m else []
    assert must_report, "control: could not read the must-report extension list for 3.1"
    promoted31 = sorted(n for n, e in ext.items() if e.get("promotedto") == "CL_VERSION_3_1")
    print("3.1 must-report list:", len(must_report), " registry promotedto 3.1:", len(promoted31))

    # ---------------- extension spec text -> optional-feature interaction (heuristic)
    inter, words = {}, {}
    for n, e in ext.items():
        sp = e.get("spec")
        if not sp or not e["present"]:
            continue
        txt = show(DOCS, "v3.1.2", "%s/%s.asciidoc" % (sp["dir"], n)) or show(DOCS, "v3.1.2", "%s/%s.txt" % (sp["dir"], n)) or ""
        words[n] = len(txt.split())
        hits = {k: len(re.findall(p, txt, re.I)) for k, p in OPT_KEYWORDS.items()}
        inter[n] = {k: v for k, v in hits.items() if v}
    assert inter, "control: no extension texts read"
    for n in ext:
        ext[n]["words"] = words.get(n)
        ext[n]["mentions"] = inter.get(n, {})

    # ---------------- structure: headings + refpages
    heads = [h for h in struct["headings"] if not h["path"][-1].startswith("refpage:")]
    refs = [h for h in struct["headings"] if h["path"][-1].startswith("refpage:")]
    refmap = [{"doc": h["doc"], "api": h["path"][-1][8:], "section": h["path"][:-1], "first": h["first"], "last": h["last"], "file": h["file"]} for h in refs]

    # ---------------- version-requirement sites (extracted lines naming 3.1) by area
    model = {
        "provenance": {"docs": {t["tag"]: {"date": t["date"], "commit": t["commit"]} for t in tags},
                       "headers": hdr["refs"], "built_from": "sources/OpenCL-Docs.git, sources/OpenCL-Headers.git"},
        "tags": tnames, "core": core, "extensions": ext, "diffs": diffs, "precedent": prec,
        "must_report_3_1": must_report, "promoted_3_1": promoted31,
        "headings": heads, "refpages": refmap, "sizes": struct["sizes"],
        "changes": chg["entries"], "optional": opt["features"], "optional_keywords": list(OPT_KEYWORDS),
        "touch": tp, "headers": {"refs": hdr["refs"], "reconcile": hdr["reconcile"],
                                 "symbols": {k: v for k, v in hdr["symbols"].items() if v["last"] == "main" and v["guard"] in ("3.0", "3.1")}},
        "header_symbols_by_guard": dict(collections.Counter(v["guard"] for v in hdr["symbols"].values() if v["last"] == "main")),
    }
    # ---------------- stored workbench results (scenarios, proposals). wip-* = other people's in-flight branches: excluded unless --include-wip
    include_wip = "--include-wip" in sys.argv
    res_dir = os.path.join(ROOT, "workbench", "results")
    results, skipped = [], []
    def clean_paths(o):
        if isinstance(o, str): return o.replace(ROOT, "<repo>")
        if isinstance(o, list): return [clean_paths(x) for x in o]
        if isinstance(o, dict): return {k: clean_paths(v) for k, v in o.items()}
        return o
    if os.path.isdir(res_dir):
        for fn in sorted(os.listdir(res_dir)):
            if not fn.endswith(".json") or fn.startswith(("calibration", "concerns")): continue
            r = json.load(open(os.path.join(res_dir, fn)))
            if "id" not in r or "checks" not in r: continue          # only run results belong here
            if r["id"].startswith("wip-") and not include_wip:
                skipped.append(r["id"]); continue
            r["kind"] = "proposal" if r["asks"] and r["asks"][0]["type"] == "proposal" else "scenario"
            if "synthetic" in r: r["synthetic"].pop("names", None)
            results.append(clean_paths(r))
    cal = os.path.join(res_dir, "calibration-3.1.json")
    model["results"] = results
    model["calibration"] = json.load(open(cal)) if os.path.exists(cal) else None
    cj = os.path.join(res_dir, "concerns.json")
    model["concerns"] = clean_paths(json.load(open(cj))) if os.path.exists(cj) else None
    print("results embedded:", len(results), " withheld (wip):", skipped)
    model["glossary"] = json.load(open(os.path.join(ROOT, "tools", "glossary.json")))
    # names the Propose tab checks against (all defined names in the latest registry, existing feature macros, example spec)
    import workbench as wb
    rx = wb.reg_index(show(DOCS, "v3.1.2", "xml/cl.xml"))
    groups = sorted({g for v in rx["enum_defs"].values() for g, _ in v if g and (g.endswith("_info") or g.endswith("_ext") or g.endswith("_khr") or g in ("cl_channel_type",))})
    model["names"] = {"enum": sorted(rx["enum_defs"]), "command": sorted(rx["cmd_defs"]), "type": sorted(rx["type_defs"]), "ext": sorted(rx["ext"]),
                      "macro": sorted(wb.existing_feature_macros()), "groups": groups}
    model["example_spec"] = json.load(open(os.path.join(ROOT, "tools", "proposals", "example-wizard.json")))
    path = os.path.join(DATA, "model.json")
    json.dump(model, open(path, "w"), separators=(",", ":"))
    print("model.json", os.path.getsize(path) // 1024, "KB;", "extensions", len(ext), "core features", len(core), "diffs", len(diffs))
    print("extension status:", dict(collections.Counter(e["status"] for e in ext.values())))
    print("precedent rows:", len(prec), " e.g.", [p for p in prec if p["to"] == "3.1"][:2])


if __name__ == "__main__":
    main()
