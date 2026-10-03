#!/usr/bin/env python3
"""Parse xml/cl.xml at every docs tag that has it -> data/registry.json.

Extracted, not asserted: all structure comes from the Khronos registry file.
Controls (printed, and asserted) guard against the silent-negative failure mode.
"""
import json, re, sys, collections
import xml.etree.ElementTree as ET
from common import *

DEP_RE = re.compile(r"deprecated in OpenCL (\d+\.\d+)")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse(xml_text):
    root = ET.fromstring(xml_text)
    # symbol definitions: enum -> group, command -> signature
    enum_group, enum_value = {}, {}
    for g in root.iter("enums"):
        for e in g.findall("enum"):
            enum_group[e.get("name")] = g.get("name")
            enum_value[e.get("name")] = e.get("value") or ("bit %s" % e.get("bitpos") if e.get("bitpos") else None)
    commands = {}
    for c in root.iter("command"):
        proto = c.find("proto")
        if proto is None:
            continue
        name = proto.findtext("name")
        attrs = (c.get("prefix") or "") + " " + (c.get("suffix") or "")
        m = re.search(r"VERSION_(\d)_(\d)_DEPRECATED", attrs)
        commands[name] = {"sig": "".join(proto.itertext()).strip(),
                          "deprecated_attr": "%s.%s" % m.groups() if m else ""}

    def reqs(parent):
        out = []
        for rq in parent.findall("require"):
            for ch in rq:
                if ch.tag in ("enum", "command", "type"):
                    out.append({"kind": ch.tag, "name": ch.get("name"),
                                "group": rq.get("comment") or "",
                                "depends": rq.get("depends") or rq.get("condition") or ""})
        return out

    features = {}
    for f in root.iter("feature"):
        syms, dep = [], {}
        for rq in f.findall("require"):
            m = DEP_RE.search(rq.get("comment") or "")
            for ch in rq:
                if ch.tag in ("enum", "command", "type"):
                    syms.append({"kind": ch.tag, "name": ch.get("name"), "group": rq.get("comment") or ""})
                    if m:
                        dep[ch.get("name")] = m.group(1)
        for s_ in syms:
            if s_["kind"] == "command" and commands.get(s_["name"], {}).get("deprecated_attr"):
                dep.setdefault(s_["name"], commands[s_["name"]]["deprecated_attr"])
        features[f.get("number")] = {"name": f.get("name"), "symbols": syms, "deprecated": dep}

    exts = {}
    for e in root.iter("extension"):
        d = e.get("depends") or ""
        exts[e.get("name")] = {
            "revision": e.get("revision"),
            "ratified": e.get("ratified") or "",
            "experimental": e.get("experimental") == "true",
            "promotedto": e.get("promotedto") or "",
            "obsoletedby": e.get("obsoletedby") or "",
            "depends": d,
            "depends_on": sorted(set(i for i in IDENT.findall(d) if i not in ("and", "or", "not"))),
            "condition": e.get("condition") or "",
            "comment": e.get("comment") or "",
            "symbols": reqs(e),
        }
    return {"features": features, "extensions": exts, "enum_group": enum_group,
            "enum_value": enum_value, "commands": commands}


def main():
    tags = docs_tags()
    out = {"source": "KhronosGroup/OpenCL-Docs xml/cl.xml", "tags": []}
    prev = None
    for t in tags:
        p = parse(show(DOCS, t["tag"], "xml/cl.xml"))
        t = dict(t, **p)
        out["tags"].append(t)
        print("%-22s %s  features=%d extensions=%d" % (t["tag"], t["date"], len(p["features"]), len(p["extensions"])))
    last = out["tags"][-1]

    # ---- controls: a negative must be provable from a positive in the same run
    f31 = last["features"]["3.1"]["symbols"]
    names31 = {s["name"] for s in f31}
    assert "clGetKernelSuggestedLocalWorkSize" in names31, "control: known 3.1 command missing"
    assert "CL_DEVICE_UUID" in names31, "control: known 3.1 enum missing"
    assert last["extensions"]["cl_khr_subgroup_rotate"]["promotedto"] == "CL_VERSION_3_1", "control: known promotion"
    nd = sum(len(f["deprecated"]) for f in last["features"].values())
    n_attr = sum(1 for c in last["commands"].values() if c["deprecated_attr"])
    n_comment = sum(1 for f in last["features"].values() for s_ in f["deprecated"] if s_ not in last["commands"] or not last["commands"][s_]["deprecated_attr"])
    # raw count straight from the text, independent of the parser
    raw = show(DOCS, last["tag"], "xml/cl.xml")
    raw_attr = len(re.findall(r"VERSION_\d_\d_DEPRECATED", raw))
    assert n_attr > 0 and n_comment > 0, "control: both deprecation encodings must yield entries"
    print("deprecation: %d via command attrs, %d via require-comments only; raw DEPRECATED mentions in xml=%d" % (n_attr, n_comment, raw_attr))
    # the control above is project-wide; also check one named item per claim type
    assert last["features"]["1.0"]["deprecated"].get("clCreateImage2D") == "1.2", "control: clCreateImage2D deprecated in 1.2"
    assert last["extensions"]["cl_khr_unified_svm"]["experimental"] is True
    print("controls OK; deprecated entries (latest tag):", nd)

    for t in out["tags"][:-1]:          # symbol tables are only needed once (latest tag)
        for k in ("enum_group", "enum_value", "commands"):
            t.pop(k)
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "registry.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("wrote data/registry.json", os.path.getsize(os.path.join(DATA, "registry.json")), "bytes")


if __name__ == "__main__":
    main()
