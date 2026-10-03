#!/usr/bin/env python3
"""Build site/ for static hosting (GitHub Pages or any web server).

  index.html     the explorer (one self-contained file)
  vote.html      the companion voting page (reads GitHub reactions)
  concerns.json  the concern lines the vote page shows (snapshot kept in site-data/)
  hidden.json    ids of reply comments the owner has hidden from the vote page (site-data/hidden.json)
  config.json    which repository the votes live in (from GITHUB_REPOSITORY, or --repo OWNER/NAME)

Links such as index.html#compare?ca=v3.0.19&cb=v3.1.0 work because the view state lives in the URL hash.
"""
import json, os, shutil, subprocess, sys
from common import *

src = os.path.join(ROOT, "opencl-explorer.html")
assert os.path.exists(src), "build the explorer first: tools/regen.sh"
html = open(src).read()
assert "/home/" not in html, "local path in the page"
assert "not affiliated with or endorsed by Khronos" in html, "attribution footer missing"
assert "VIEWS.propose" in html and "VIEWS.help" in html, "page is out of date"
repo = os.environ.get("GITHUB_REPOSITORY", "")
if "--repo" in sys.argv: repo = sys.argv[sys.argv.index("--repo") + 1]
if not repo:
    try:
        url = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
        repo = url.replace("https://github.com/", "").replace("git@github.com:", "").removesuffix(".git") if "github.com" in url else ""
    except Exception: repo = ""
out = os.path.join(ROOT, "site"); os.makedirs(out, exist_ok=True)
shutil.copy(src, os.path.join(out, "index.html"))
cj = os.path.join(ROOT, "site-data", "concerns.json")
assert os.path.exists(cj), "site-data/concerns.json missing (run tools/regen.sh to refresh it)"
shutil.copy(cj, os.path.join(out, "concerns.json"))
hj = os.path.join(ROOT, "site-data", "hidden.json")
if not os.path.exists(hj): json.dump({"comments": []}, open(hj, "w"))
shutil.copy(hj, os.path.join(out, "hidden.json"))
vote = open(os.path.join(ROOT, "tools", "vote_template.html")).read()
assert "/home/" not in vote
open(os.path.join(out, "vote.html"), "w").write(vote)
json.dump({"repo": repo}, open(os.path.join(out, "config.json"), "w"))
open(os.path.join(out, ".nojekyll"), "w").write("")
open(os.path.join(out, "robots.txt"), "w").write("User-agent: *\nAllow: /\n")
print("site/ ready: index.html (%d KB), vote.html, concerns.json, config.json (repo=%r), .nojekyll, robots.txt" % (len(html) // 1024, repo))
