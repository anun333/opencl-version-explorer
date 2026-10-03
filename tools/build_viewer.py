#!/usr/bin/env python3
"""Inline data/model.json into the template -> opencl-explorer.html (opens from file://).

The wording of appendix H (table rows and prose) is withheld from the page: its source file states no licence.
Names, counts and a link to the spec stay.  Set KEEP_APPENDIX_H=1 for a private build that keeps the text.
"""
import json, os
from common import *

tpl = open(os.path.join(ROOT, "tools", "viewer_template.html")).read()
m = json.load(open(os.path.join(DATA, "model.json")))
keep = os.environ.get("KEEP_APPENDIX_H") == "1"
if not keep:
    for f in m["optional"]:
        for r in f["rows"]: r.pop("behaviour", None)
        f["text"] = ""; f["withheld"] = True
model = json.dumps(m, separators=(",", ":")).replace("</", "<\\/")
assert "/*__MODEL__*/" in tpl
out = tpl.replace("/*__MODEL__*/", model)
assert "/home/" not in out, "local path leaked into the page"
if not keep:
    for phrase in ("indicating that device does not support Shared Virtual Memory", "Returns CL_INVALID_OPERATION if the device associated with"):
        assert phrase not in out, "appendix H wording is still in the page: " + phrase
dst = os.path.join(ROOT, "opencl-explorer.html")
open(dst, "w").write(out)
print("wrote", dst, len(out) // 1024, "KB;", "appendix H wording kept (private build)" if keep else "appendix H wording withheld")
