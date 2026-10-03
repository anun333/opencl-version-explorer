#!/usr/bin/env python3
"""Create the GitHub issues and comments the vote page reads.  One issue per direction; one comment per votable concern.

    python3 tools/seed_votes.py OWNER/REPO --site-url https://OWNER.github.io/REPO/ [--dry-run]

Idempotent: items are found again by the hidden markers <!-- vote-direction: ID --> and <!-- vote-item: ID -->,
so re-running only adds what is missing.  Votes are GitHub reactions on these issues and comments.
Uses the GitHub CLI (`gh`) with whatever account is logged in; that account must own the repository.
"""
import json, subprocess, sys, time, os, re
from common import *

repo = sys.argv[1]; dry = "--dry-run" in sys.argv
site = sys.argv[sys.argv.index("--site-url") + 1] if "--site-url" in sys.argv else ""
data = json.load(open(os.path.join(ROOT, "site-data", "concerns.json")))
VOTABLE = lambda c: c["level"] in ("high", "notable") and c["source"] != "NOT KNOWABLE"


def gh(*args, body=None):
    cmd = ["gh", "api", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, input=body)
    if r.returncode: sys.exit("gh failed: %s\n%s" % (" ".join(cmd[:5]), r.stderr.strip()))
    return json.loads(r.stdout) if r.stdout.strip() else None


def post(path, payload):
    if dry: return {"number": 0, "html_url": "(dry run)"}
    time.sleep(1.5)                                   # stay clear of GitHub's secondary rate limits
    return gh("-X", "POST", path, "--input", "-", body=json.dumps(payload))


def pages(path):
    out = []
    for p in range(1, 8):
        j = gh("%s%sper_page=100&page=%d" % (path, "&" if "?" in path else "?", p)) or []
        out += j
        if len(j) < 100: break
    return out


issues = {m.group(1): i for i in pages("repos/%s/issues?state=all" % repo) if not i.get("pull_request") for m in [re.search(r"<!-- vote-direction: ([\w-]+) -->", i.get("body") or "")] if m}
made_i = made_c = 0
for d in data["directions"]:
    items = [c for c in d["concerns"] if VOTABLE(c)]
    iss = issues.get(d["id"])
    if not iss:
        body = ("<!-- vote-direction: %s -->\n**%s**\n\n%s\n\nThis is a hypothetical direction for a future OpenCL version, produced by an independent tool from Khronos's public files. It is not a Khronos plan.\n\n"
                "**React to this post** to vote on the direction: 👍 = I would want this explored for a future version, 👎 = I would not.\n"
                "**React to each comment below** to vote on that concern: 👍 = I agree it is a real concern, 👎 = I don't think so, or I think it is wrong (please reply with why).\n\n"
                "Counts are shown on the vote page%s. One reaction per person; informal and unweighted.") % (d["id"], d["title"], d.get("intent") or "", (": " + site + "vote.html") if site else "")
        iss = post("repos/%s/issues" % repo, {"title": "Direction: " + d["title"], "body": body}); made_i += 1
        print("issue  %-4s %s" % (iss["number"], d["title"]))
    existing = set()
    if iss["number"]:
        for c in pages("repos/%s/issues/%d/comments" % (repo, iss["number"])):
            m = re.search(r"<!-- vote-item: ([\w-]+) -->", c.get("body") or "")
            if m: existing.add(m.group(1))
    for c in items:
        if c["id"] in existing: continue
        body = "<!-- vote-item: %s -->\n**%s** · %s\n\n%s\n\n_👍 = I agree this is a real concern for this direction. 👎 = I don't think so, or I think it is wrong._" % (c["id"], c["level"], c["source"].lower(), c["text"])
        post("repos/%s/issues/%d/comments" % (repo, iss["number"]), {"body": body}); made_c += 1
print("%s: %d issue(s) and %d comment(s) %s" % ("dry run" if dry else "done", made_i, made_c, "would be created" if dry else "created"))
