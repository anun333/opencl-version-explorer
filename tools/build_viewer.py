#!/usr/bin/env python3
"""Inline data/model.json into the template -> opencl-explorer.html (opens from file://)."""
import os
from common import *

tpl = open(os.path.join(ROOT, "tools", "viewer_template.html")).read()
model = open(os.path.join(DATA, "model.json")).read().replace("</", "<\\/")
assert "/*__MODEL__*/" in tpl
out = tpl.replace("/*__MODEL__*/", model)
assert "/home/" not in out, "local path leaked into the page"
dst = os.path.join(ROOT, "opencl-explorer.html")
open(dst, "w").write(out)
print("wrote", dst, len(out) // 1024, "KB")
