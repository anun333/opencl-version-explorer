#!/usr/bin/env python3
"""Where did introducing OpenCL 3.1 touch the docs repo?  -> data/touchpoints.json

1. area-level churn between v3.0.19 and v3.1.0 (git numstat grouped by area)
2. every line of the v3.1.2 tree that names OpenCL 3.1 (a version-bump checklist)
3. the same literal scan over the headers at v2026.05.29
"""
import re, json, collections
from common import *

LIT = re.compile(r"(OpenCL(?: C)?[ _]3\.1|CL_VERSION_3_1|VERSION_3_1|\b310\b|CL3\.1|OpenCL 3\.1|newer than 3\.0|3\.1 or newer|v3\.1)")


def area(p):
    if p.startswith("api/cl_") or p.startswith("extensions/") or p.startswith("ext/"):
        return "extension specs"
    for pre, a in (("api/", "API spec"), ("c/", "OpenCL C spec"), ("env/", "SPIR-V env spec"), ("cxx", "C++ specs"),
                   ("xml/", "registry (cl.xml)"), ("man/", "refpage static"), ("scripts/", "scripts"),
                   ("config/", "build config"), ("langext/", "language ext"), (".github", "CI")):
        if p.startswith(pre):
            return a
    return "top level / other"


def main():
    num = git(DOCS, "diff", "--numstat", "v3.0.19", "v3.1.0").splitlines()
    ch = collections.defaultdict(lambda: {"files": 0, "added": 0, "deleted": 0})
    files = []
    for l in num:
        a, d, p = l.split("\t")
        if a == "-":
            continue
        c = ch[area(p)]; c["files"] += 1; c["added"] += int(a); c["deleted"] += int(d)
        c.setdefault("trivial", 0)
        if int(a) + int(d) <= 2:
            c["trivial"] += 1          # <=2 changed lines: almost always the copyright-year bump
        files.append({"path": p, "area": area(p), "added": int(a), "deleted": int(d)})
    sites = []
    for p in ls_tree(DOCS, "v3.1.2"):
        if p.startswith(("katex/", "images/", "config/rouge")) or not p.endswith((".asciidoc", ".txt", ".xml", ".py", ".adoc", ".md", ".yml", "Makefile", "makeSpec")):
            continue
        txt = show(DOCS, "v3.1.2", p)
        for n, line in enumerate((txt or "").splitlines(), 1):
            if LIT.search(line) and not re.search(r"OpenGL 3\.1|GL 3\.1|Vulkan", line):
                sites.append({"path": p, "line": n, "area": area(p), "text": line.strip()[:240]})
    by = collections.Counter(s["area"] for s in sites)
    hs = []
    for p in ls_tree(HDRS, "v2026.05.29", "CL"):
        for n, line in enumerate((show(HDRS, "v2026.05.29", p) or "").splitlines(), 1):
            if re.search(r"VERSION_3_1|\b310\b", line):
                hs.append({"path": p, "line": n, "text": line.strip()[:200]})
    # controls: known sites must be found
    assert any(s["path"] == "api/opencl_architecture.asciidoc" and "SPIR-V 1.4" in s["text"] for s in sites), "control: architecture requirements line"
    assert any(s["path"] == "xml/cl.xml" and "CL_VERSION_3_1" in s["text"] for s in sites), "control: registry feature element"
    assert any("cl_version.h" in h["path"] for h in hs), "control: cl_version.h"
    print("area churn v3.0.19->v3.1.0:", {k: v for k, v in ch.items()})
    print("version-literal sites in tree:", len(sites), dict(by), " header sites:", len(hs))
    json.dump({"churn": ch, "files": files, "sites": sites, "header_sites": hs,
               "from": "v3.0.19", "to": "v3.1.0", "tree": "v3.1.2"},
              open(os.path.join(DATA, "touchpoints.json"), "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
