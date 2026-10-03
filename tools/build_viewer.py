#!/usr/bin/env python3
"""Inline data/model.json into the template -> opencl-explorer.html (opens from file://).

Appendix H of the API specification (table rows and prose) is shown, attributed under CC BY 4.0: the repository's LICENSE and README
say the specification sources are CC BY 4.0, although this one file has no header of its own (see CREDITS.md).
Set WITHHOLD_APPENDIX_H=1 to build a page that omits the wording (names, counts and a link to the spec stay).
"""
import json, os
from common import *

tpl = open(os.path.join(ROOT, "tools", "viewer_template.html")).read()
m = json.load(open(os.path.join(DATA, "model.json")))
withhold = os.environ.get("WITHHOLD_APPENDIX_H") == "1"
if withhold:
    for f in m["optional"]:
        for r in f["rows"]: r.pop("behaviour", None)
        f["text"] = ""; f["withheld"] = True
m.setdefault("features", {})["appendix_h_withheld"] = withhold
model = json.dumps(m, separators=(",", ":")).replace("</", "<\\/")
assert "/*__MODEL__*/" in tpl
out = tpl.replace("/*__MODEL__*/", model)
assert "/home/" not in out, "local path leaked into the page"
phrase = "indicating that device does not support Shared Virtual Memory"
if withhold: assert phrase not in out, "appendix H wording is still in the page"
else: assert phrase in out and "Creative Commons Attribution 4.0" in out, "appendix H is expected in the page, with its attribution"
dst = os.path.join(ROOT, "opencl-explorer.html")
open(dst, "w").write(out)
print("wrote", dst, len(out) // 1024, "KB;", "appendix H wording withheld" if withhold else "appendix H shown with CC BY attribution")
