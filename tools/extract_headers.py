#!/usr/bin/env python3
"""OpenCL-Headers at every tag (+ main) -> data/headers.json

For each CL/*.h: symbols (#define CL_* constants and cl* functions) with the
innermost CL_VERSION_x_y guard they sit under, and deprecation markers.
Then reconcile against the registry (cl.xml) at the docs tag nearest in time.
"""
import re, json, collections
from common import *

GUARD = re.compile(r"^\s*#\s*(?:ifdef\s+CL_VERSION_(\d)_(\d)|if\s+defined\s*\(\s*CL_VERSION_(\d)_(\d)\s*\)|if\s+CL_TARGET_OPENCL_VERSION\s*>=\s*(\d)(\d)0)\b")
DEFINE = re.compile(r"^\s*#\s*define\s+(CL_[A-Za-z0-9_]+)(?!\()\b(.*)$")
FUNC = re.compile(r"CL_API_ENTRY[^;{]*?\b(cl[A-Z][A-Za-z0-9_]*)\s*\(([^;]*?)\)\s*([A-Z_0-9 ]*?);", re.S)
SKIP_PREFIX = ("CL_API_", "CL_CALLBACK", "CL_EXT_PREFIX", "CL_EXT_SUFFIX", "CL_TARGET", "CL_HAS_", "CL_USE_DEPRECATED")


def vt(m):
    g = [x for x in m.groups() if x]
    return "%s.%s" % (g[0], g[1])


def scan_file(txt):
    lines = txt.splitlines()
    stack, guard_at = [], []
    syms = {}
    for i, line in enumerate(lines):
        s = line.strip()
        g = GUARD.match(line)
        if g:
            stack.append(vt(g))
        elif re.match(r"^\s*#\s*(if|ifdef|ifndef)\b", line):
            stack.append(None)
        elif re.match(r"^\s*#\s*(else|elif)\b", line):
            if stack:
                stack[-1] = None
        elif re.match(r"^\s*#\s*endif\b", line):
            if stack:
                stack.pop()
        cur = [x for x in stack if x]
        guard_at.append(max(cur, key=vkey) if cur else "")
        d = DEFINE.match(line)
        if d and re.match(r"^CL_VERSION_\d_\d$", d.group(1)):
            d = None                       # the version-guard macros themselves are not API
        if d and not d.group(1).startswith(SKIP_PREFIX) and not d.group(1).endswith("_H"):
            syms[d.group(1)] = {"kind": "enum", "guard": guard_at[-1],
                                "deprecated": "deprecated" in d.group(2).lower()}
    offs, o = [], 0
    for l in lines:
        offs.append(o); o += len(l) + 1
    import bisect
    for m in FUNC.finditer(txt):
        ln = bisect.bisect_right(offs, m.start()) - 1
        # guard of the declaration statement itself (the line holding the name)
        ln_name = bisect.bisect_right(offs, m.start(1)) - 1
        suffix = m.group(3).strip() + " " + txt[m.start():m.start(1)]
        dm = re.search(r"VERSION_(\d)_(\d)_DEPRECATED", suffix)
        sm = re.search(r"CL_API_SUFFIX__VERSION_(\d)_(\d)\b(?!_)", m.group(0))
        syms[m.group(1)] = {"kind": "command", "guard": guard_at[ln_name],
                            "deprecated": bool(dm), "deprecated_in": "%s.%s" % dm.groups() if dm else "",
                            "suffix_version": "%s.%s" % sm.groups() if sm else ""}
    return syms


def snapshot(ref):
    out = {}
    for p in ls_tree(HDRS, ref, "CL"):
        if not p.endswith(".h"):
            continue
        for name, v in scan_file(show(HDRS, ref, p)).items():
            v["file"] = os.path.basename(p)
            out.setdefault(name, v)
    return out


def main():
    tags = git(HDRS, "tag", "--sort=creatordate").split()
    refs = tags + ["main"]
    snaps = {}
    meta = []
    for r in refs:
        snaps[r] = snapshot(r)
        d, sha = git(HDRS, "log", "-1", "--format=%cs %H", r).split()
        meta.append({"ref": r, "date": d, "commit": sha, "symbols": len(snaps[r])})
        print("%-12s %s %5d symbols" % (r, d, len(snaps[r])))

    # ---- controls: one named item per claim
    last = snaps["v2026.05.29"]
    assert last["clGetKernelSuggestedLocalWorkSize"]["guard"] == "3.1", last.get("clGetKernelSuggestedLocalWorkSize")
    assert "clGetKernelSuggestedLocalWorkSize" not in snaps["v2025.07.22"], "3.1 command must not exist before the 3.1 header"
    assert last["CL_DEVICE_UUID"]["guard"] == "3.1" and last["CL_DEVICE_MAX_WORK_GROUP_SIZES"]["guard"] == "3.1"
    assert snaps["v2023.12.14"]["CL_DEVICE_HOST_UNIFIED_MEMORY"]["deprecated"] and not last["CL_DEVICE_HOST_UNIFIED_MEMORY"]["deprecated"], "control: un-deprecation visible in headers"
    assert snaps["v2023.12.14"]["clCreateImage2D"]["deprecated"], "control: clCreateImage2D deprecated suffix"
    assert sum(1 for v in last.values() if v["guard"] == "3.0") > 20

    # ---- lifecycle: first/last ref per symbol, guard at the latest ref
    life = {}
    for r in refs:
        for n, v in snaps[r].items():
            e = life.setdefault(n, {"first": r, "kind": v["kind"], "file": v["file"]})
            e["last"] = r
            e["guard"] = v["guard"]
            e["deprecated"] = v["deprecated"]
            e["deprecated_in"] = v.get("deprecated_in", "")
    # ---- reconcile with the registry (latest docs tag)
    reg = json.load(open(os.path.join(DATA, "registry.json")))["tags"][-1]
    rows = []
    for ver, f in reg["features"].items():
        for s in f["symbols"]:
            if s["kind"] == "type":
                continue
            h = snaps["main"].get(s["name"])
            hg = h["guard"] if h else None
            exp = ver if vkey(ver) >= (1, 0) else ""
            ok = (h is not None) and ((hg == ver) or (hg == "" and vkey(ver) < (2, 0)) or (vkey(ver) < (2, 0) and hg.startswith("1.")) )
            if h is None or not ok:
                rows.append({"name": s["name"], "registry": ver, "header_guard": hg if h else "(missing)"})
    n_reg = sum(1 for f in reg["features"].values() for s in f["symbols"] if s["kind"] != "type")
    print("registry core symbols (enum/command):", n_reg, " header disagreements:", len(rows))
    c = collections.Counter((r["registry"], r["header_guard"]) for r in rows)
    print("disagreement classes (registry feature, header guard):", c.most_common(12))
    json.dump({"refs": meta, "symbols": life, "reconcile": rows,
               "note": "guard is the innermost CL_VERSION_x_y guard at the latest ref; '' means unguarded"},
              open(os.path.join(DATA, "headers.json"), "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
