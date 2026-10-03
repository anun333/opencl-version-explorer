#!/usr/bin/env python3
"""Spec outline per tag -> data/structure.json

For each docs tag and each spec (API, C, Env, Ext) follow static include::
lines from the entry file, collect headings, and record for every heading
path the first and last tag it was seen in.  Extension chapter files
(api/cl_*, extensions/cl_*, ext/cl_*) are tracked by existence per tag.
"""
import re, json, collections
from common import *

ENTRY = {"API": "OpenCL_API.txt", "C": "OpenCL_C.txt", "Env": "OpenCL_Env.txt", "Ext": "OpenCL_Ext.txt"}
INC = re.compile(r"^include::([^{}\[\]]+)\[[^\]]*\]\s*$")
REFP = re.compile(r"^\[open,refpage='([^']+)'(?:,desc='([^']*)')?(?:,type='([^']*)')?")
HEAD = re.compile(r"^(={1,6}) (\S.*?)\s*$")


def outline(tag, entry):
    """Return (headings, files, words) for one spec at one tag."""
    heads, files, words = [], [], 0
    seen = set()

    def walk(path):
        nonlocal words
        if path in seen:
            return
        seen.add(path)
        txt = show(DOCS, tag, path)
        if txt is None:
            return
        files.append(path)
        words += len(txt.split())
        in_block = None
        for n, line in enumerate(txt.splitlines(), 1):
            if line.startswith(("----", "....", "////")) and len(line.strip()) >= 4 and set(line.strip()) <= set("-./"):
                in_block = None if in_block == line.strip() else (in_block or line.strip())
                continue
            if in_block:
                continue
            m = INC.match(line)
            if m:
                walk(m.group(1))
                continue
            r = REFP.match(line)
            if r:
                heads.append((-1, "refpage:" + r.group(1), path, n))
                continue
            h = HEAD.match(line)
            if h:
                heads.append((len(h.group(1)), h.group(2), path, n))

    walk(entry)
    return heads, files, words


def paths(heads):
    stack, out = [], []                      # stack of (level, title)
    for lvl, title, f, n in heads:
        if lvl == -1:
            out.append((-1, tuple(t for _, t in stack) + (title,), f))
            continue
        title = title.replace("^(TM)^", "\u2122").replace("^(R)^", "\u00ae")
        title = re.sub(r"\s+", " ", re.sub(r"[`*_]|\{[^}]*\}|\^[^^]*\^", "", title)).strip()
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        stack.append((lvl, title))
        out.append((lvl, tuple(t for _, t in stack), f))
    return out


def main():
    tags = [t["tag"] for t in docs_tags()]
    spec = collections.OrderedDict()      # (doc, path) -> {first,last,level,file}
    sizes = {}
    extfiles = collections.OrderedDict()  # file -> {first,last}
    for tag in tags:
        sizes[tag] = {}
        for doc, entry in ENTRY.items():
            heads, files, words = outline(tag, entry)
            if not files:
                continue
            sizes[tag][doc] = {"headings": len(heads), "files": len(files), "words": words}
            for lvl, path, f in paths(heads):
                k = (doc, path, f)
                e = spec.setdefault(k, {"first": tag, "level": lvl, "file": f})
                e["last"] = tag
        for p in ls_tree(DOCS, tag):
            m = re.match(r"^(api|extensions|ext)/(cl_[A-Za-z0-9_]+)\.(asciidoc|txt)$", p)
            if m:
                e = extfiles.setdefault(m.group(2), {"first": tag, "dir": m.group(1)})
                e["last"] = tag
                e["dir"] = m.group(1)
    last = tags[-1]

    # ---- controls (each as specific as the claim it guards)
    assert sizes[last]["API"]["headings"] > 200, "API outline implausibly small: %s" % sizes[last]["API"]
    assert sizes[last]["C"]["headings"] > 100, "C outline implausibly small"
    assert sizes[last]["Env"]["headings"] > 20, "Env outline implausibly small"
    assert "Ext" not in sizes[last], "OpenCL_Ext.txt must be gone in 3.1.2"
    assert "Ext" in sizes["v3.0.19"], "OpenCL_Ext.txt must exist in 3.0.19"
    refs = [k for k in spec if k[0] == "API" and k[1][-1].startswith("refpage:")]
    assert any(k[1][-1] == "refpage:clGetDeviceInfo" for k in refs), "control: refpage clGetDeviceInfo"
    assert any(k[1][-1] == "refpage:clGetKernelSuggestedLocalWorkSize" for k in spec if k[0] == "API"), "control: 3.1 refpage"
    assert any(k[1][-1] == "Shared Virtual Memory" and k[2] == "api/opencl_runtime_layer.asciidoc" for k in spec), "control: runtime-layer SVM section"
    print("API refpages (all tags):", len(refs))
    for must in [("API", ("The OpenCL Architecture", "Platform Model"), "api/opencl_architecture.asciidoc"),
                 ("API", ("OpenCL 3.0 Backwards Compatibility", "Shared Virtual Memory"), "api/appendix_h.asciidoc"),
                 ]:
        assert must in spec, "control: heading missing %r" % (must,)
    assert "cl_khr_unified_svm" in extfiles and "cl_khr_command_buffer" in extfiles
    # the extension files should account for extensions the registry knows (cross-check, reported not asserted)
    reg = json.load(open(os.path.join(DATA, "registry.json")))["tags"][-1]["extensions"]
    miss = sorted(e for e in reg if e not in extfiles and reg[e]["symbols"])
    print("registry extensions with symbols but no spec file:", len(miss), miss[:12])

    out = {"tags": tags, "sizes": sizes,
           "headings": [{"doc": d, "path": list(p), "level": v["level"], "first": v["first"],
                         "last": v["last"], "file": v["file"]} for (d, p, _f), v in spec.items()],
           "extfiles": [dict(name=k, **v) for k, v in extfiles.items()]}
    json.dump(out, open(os.path.join(DATA, "structure.json"), "w"), separators=(",", ":"))
    print("headings:", len(out["headings"]), " ext files:", len(out["extfiles"]))
    for d in ("API", "C", "Env", "Ext"):
        for t in ("v3.0.19", last):
            if d in sizes.get(t, {}):
                print(" ", d, t, sizes[t][d])


if __name__ == "__main__":
    main()
