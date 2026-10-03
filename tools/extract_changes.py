#!/usr/bin/env python3
"""Changelogs of the API spec (appendix E) and OpenCL C spec (appendix A) at v3.1.2
-> data/changes.json, one entry per bullet with the API/enum/extension names it cites.

`kind` is a keyword heuristic over the bullet text, not something the spec states.
"""
import re, json, collections
from common import *

TAG = "v3.1.2"
SRC = [("API", "api/appendix_e.asciidoc"), ("C", "c/appendix_a.asciidoc")]
BIG = re.compile(r"^== Summary of [Cc]hanges (?:from|to) OpenCL (\d+\.\d+)(?: to OpenCL (\d+\.\d+))?")
SMALL = re.compile(r"^Changes from \*(v[\d.]+)\*(?: to \*(v[\d.]+)\*)?:")
MACRO = re.compile(r"\{([A-Za-z0-9_]+)\}")
PR = re.compile(r"(?:khronos-opencl-(?:pr|issue)\}/(\d+)|internal issue (\d+))")


def nxt(v):                      # v3.0.5 -> v3.0.6
    a, b, c = v[1:].split(".")
    return "v%s.%s.%d" % (a, b, int(c) + 1)


def kind(t):
    t = t.lower()
    for k, pats in (("promoted", ("promoted", "promotion")), ("deprecated", ("deprecat",)),
                    ("finalized", ("finalized", "no longer experimental")),
                    ("removed", ("removes ", "removed ", "removal")),
                    ("ext-added", ("added new extension", "adds new extension", "added the {cl_", "added version", "re-added", "new extension")),
                    ("required", ("required support", "now required", "requires support")),
                    ("clarified", ("clarif",)), ("fixed", ("fixed", "typo", "corrected")),
                    ("added", ("added", "adds ", "new queries", "new api")), ("relaxed", ("relaxed",))):
        if any(p in t for p in pats):
            return k
    return "other"


def clean(t):
    t = re.sub(r",? ?see \{khronos-opencl-(?:pr|issue)\}/\d+\[#\d+\](?: and \{khronos-opencl-(?:pr|issue)\}/\d+\[#\d+\])*", "", t)
    t = re.sub(r"\{khronos-opencl-(?:pr|issue)\}/\d+\[#(\d+)\]", r"#\1", t)
    t = MACRO.sub(lambda m: re.sub(r"_EXT$", "", m.group(1)), t)
    t = re.sub(r"\[\[[^\]]*\]\]", "", t)
    return re.sub(r"\s+", " ", t.replace("`", "")).strip()


dropped = []


def parse(doc, path):
    txt = show(DOCS, TAG, path)
    assert txt, path
    out, group, lead, cur = [], None, "", None
    parents = {}

    def flush():
        nonlocal cur
        if cur:
            raw = cur["raw"]
            ents = [m.group(1) for m in MACRO.finditer(raw)]
            cur["text"] = clean(raw)
            cur["exts"] = sorted({re.sub(r"_EXT$", "", e) for e in ents if e.endswith("_EXT")})
            cur["names"] = sorted({e for e in ents if not e.endswith("_EXT") and not e.startswith(("khronos", "opencl_c", "cl_khr", "cl_ext"))
                                   and (e.startswith(("cl", "CL_")))})
            cur["feature_macros"] = sorted({e for e in ents if e.startswith("opencl_c_")})
            cur["refs"] = sorted({a or b for a, b in PR.findall(raw)})
            cur["kind"] = kind(cur["lead"] + " " + raw)
            del cur["raw"]
            out.append(cur)
        cur = None

    for line in txt.splitlines():
        m = BIG.match(line)
        if m:
            flush(); lead = ""; parents.clear()
            fr = m.group(1); to = m.group(2)
            # "Summary of changes to OpenCL 3.0" (C spec) is the 3.0 baseline
            group = {"from": "OpenCL " + fr, "to": "OpenCL " + (to or fr), "label": "OpenCL %s" % (to or fr)}
            if not to:
                group["from"] = "(pre-3.0)"
            continue
        m = SMALL.match(line)
        if m:
            flush(); lead = ""; parents.clear()
            fr, to = m.group(1), m.group(2) or nxt(m.group(1))
            group = {"from": fr, "to": to, "label": to}
            continue
        if group is None or line.startswith(("//", "[appendix]", "[[")) or line.startswith("= "):
            continue
        b = re.match(r"^(\s*)(\*{1,4}) (.*)$", line)
        if b:
            flush()
            lv = len(b.group(2))
            cur = {"doc": doc, "from": group["from"], "to": group["to"], "label": group["label"],
                   "level": lv, "lead": clean(parents.get(lv - 1, lead)) if lv > 1 else lead, "raw": b.group(3)}
            parents[lv] = b.group(3)
            for k in [k for k in parents if k > lv]:
                del parents[k]
            continue
        if not line.strip():
            flush(); continue
        if cur is not None and (line.startswith(" ") or cur["level"] == 0):
            cur["raw"] += " " + line.strip()
        else:
            flush()
            if line.startswith("The first non-experimental") or line.startswith("NOTE:"):
                continue
            # a paragraph is itself a change statement (e.g. "OpenCL 3.1 requires SPIR-V 1.0 to 1.4")
            cur = {"doc": doc, "from": group["from"], "to": group["to"], "label": group["label"],
                   "level": 0, "lead": "", "raw": line.strip()}
            lead = clean(line)
    flush()
    # a bare "cl_khr_x" bullet that has child bullets is only a header: its children carry the content
    keep = []
    for i, r in enumerate(out):
        bare = re.fullmatch(r"[A-Za-z0-9_]+(?: \((?:experimental|final)\))?:?", r["text"]) is not None
        has_child = i + 1 < len(out) and out[i + 1]["level"] == r["level"] + 1 and out[i + 1]["to"] == r["to"] and r["level"] > 0
        if bare and has_child:
            dropped.append(r)
        else:
            keep.append(r)
    return keep


def main():
    rows = []
    for doc, path in SRC:
        rows += parse(doc, path)
    # ---- controls
    api = [r for r in rows if r["doc"] == "API"]
    assert any(r["to"] == "OpenCL 3.1" and "cl_khr_unified_svm" in r["exts"] for r in api), "control: unified_svm added in 3.1"
    assert any(r["to"] == "v3.1.1" and "CL_COMPLETE" in r["names"] for r in api), "control: 3.1.1 revert cites CL_COMPLETE"
    assert any(r["to"] == "v3.0.19" for r in api) and any(r["to"] == "OpenCL 1.1" for r in api)
    by = collections.Counter((r["doc"], r["to"]) for r in rows)
    expect_groups = len(re.findall(r"^(?:== Summary of|Changes from \*)", show(DOCS, TAG, SRC[0][1]) + show(DOCS, TAG, SRC[1][1]), re.M))
    got_groups = len({(r["doc"], r["from"], r["to"]) for r in rows})
    print("entries:", len(rows), " groups with entries:", got_groups, " group headers in text:", expect_groups)
    # bullets in text vs entries: every bullet line must have become an entry
    nb = sum(len(re.findall(r"^\s*\*{1,4} ", show(DOCS, TAG, p), re.M)) for _, p in SRC)
    nbe = sum(1 for r in rows if r["level"] > 0) + len(dropped)
    print("bullet lines in text:", nb, " bullet entries:", nbe, " paragraph entries:", len(rows) - nbe)
    assert nb == nbe, "control: bullets lost"
    print("bare header bullets dropped:", len(dropped))
    assert any(r["to"] == "OpenCL 3.1" and r["level"] == 0 and "SPIR-V 1.4" in r["text"] for r in api), "control: 3.1 SPIR-V paragraph"
    json.dump({"source": SRC, "tag": TAG, "entries": rows}, open(os.path.join(DATA, "changes.json"), "w"), separators=(",", ":"))
    print(collections.Counter(r["kind"] for r in rows).most_common())


if __name__ == "__main__":
    main()
