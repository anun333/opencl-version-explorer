#!/usr/bin/env python3
"""Appendix H (OpenCL 3.0 Backwards Compatibility) at v3.1.2 -> data/optional.json

One record per optional feature: detection/behaviour rows (API -> behaviour),
feature macros, queries, and the prose.  The same file is read at v3.0.19 so the
viewer can show what appendix H changed between 3.0 and 3.1.
"""
import re, json
from common import *

MACRO = re.compile(r"\{([A-Za-z0-9_]+)\}")


EMPH = re.compile(r"(?<![\w])_([A-Za-z]+(?:_[A-Za-z]+)*)_(?![\w])")


def parse(tag):
    txt = show(DOCS, tag, "api/appendix_h.asciidoc")
    secs, cur = [], None
    for line in txt.splitlines():
        m = re.match(r"^== (.+)$", line)
        if m:
            cur = {"title": m.group(1).strip(), "rows": [], "prose": [], "macros": [], "queries": [], "apis": []}
            secs.append(cur); continue
        if cur is None:
            continue
        cur["prose"].append(line)
    for s in secs:
        body = "\n".join(s["prose"])
        # table rows: "| API cell\n| behaviour cell" separated by blank lines inside |==== blocks
        for blk in re.findall(r"\|====\n(.*?)\n\|====", body, re.S):
            for row in re.split(r"\n\n(?=\| )", blk):
                cells = re.split(r"\n\| ", row.strip().lstrip("|").strip(), maxsplit=1) if row.strip().startswith("|") else []
                if len(cells) == 2 and not cells[0].startswith("*API*"):
                    api = re.sub(r"\s+", " ", re.sub(r"\{([^}]+)\}", r"\1", cells[0].replace(" +", ""))).strip(" ,")
                    beh = EMPH.sub(r"\1", re.sub(r"\s+", " ", re.sub(r"\{([^}]+)\}", r"\1", cells[1].replace(" +", " "))).strip())
                    s["rows"].append({"api": api, "behaviour": beh})
        ms = [m for m in MACRO.findall(body)]
        s["macros"] = sorted({m for m in ms if m.startswith("opencl_c_")})
        s["queries"] = sorted({m for m in ms if m.startswith("CL_DEVICE_") or m.startswith("CL_MEM_") or m.startswith("CL_PROGRAM_")})
        s["apis"] = sorted({m for m in ms if re.match(r"cl[A-Z]", m)})
        txt2 = re.sub(r"\|====.*?\|====", "", body, flags=re.S)
        s["text"] = EMPH.sub(r"\1", re.sub(r"\s+", " ", re.sub(r"\{([^}]+)\}", r"\1", txt2)).strip())
        del s["prose"]
    return secs


def main():
    new, old = parse("v3.1.2"), parse("v3.0.19")
    assert len(new) == 18 == len(re.findall(r"^== ", show(DOCS, "v3.1.2", "api/appendix_h.asciidoc"), re.M))
    by = {s["title"]: s for s in new}
    # controls specific to named items
    assert any("clSVMAlloc" in r["api"] for r in by["Shared Virtual Memory"]["rows"]), "control: SVM row for clSVMAlloc"
    assert "opencl_c_device_enqueue" in by["Device-Side Enqueue"]["macros"]
    assert "opencl_c_subgroups" in by["Sub-groups"]["macros"]
    assert "opencl_c_generic_address_space" in by["Generic Address Space"]["macros"]
    nrows = sum(len(s["rows"]) for s in new)
    print("features:", len(new), "rows:", nrows, "macros:", sorted({m for s in new for m in s["macros"]}))
    oldby = {s["title"]: s for s in old}
    for s in new:
        o = oldby.get(s["title"])
        s["changed_since_3_0_19"] = (o is None) or (o["rows"] != s["rows"] or o["text"] != s["text"])
    print("appendix H sections whose text/rows differ 3.0.19 -> 3.1.2:", [s["title"] for s in new if s["changed_since_3_0_19"]])
    zero = [s["title"] for s in new if not s["rows"]]
    print("sections with no table rows (prose-only or parse miss):", zero)
    json.dump({"tag": "v3.1.2", "features": new}, open(os.path.join(DATA, "optional.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
