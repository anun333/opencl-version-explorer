#!/usr/bin/env python3
"""Create the GitHub issues the vote page reads: one per direction, one per votable concern.

    python3 tools/seed_votes.py OWNER/REPO --site-url https://OWNER.github.io/REPO/ [--dry-run] [--migrate]

A vote is a GitHub reaction on an issue; a comment on the issue is a reply, shown on the vote page with its author's
GitHub name.  Items are found again by the hidden markers <!-- vote-direction: ID --> and <!-- vote-item: ID -->, so
re-running only adds what is missing and never deletes.

--migrate  one-time clean-up of the first layout (concerns as comments on direction issues): deletes those seeded
           comments, but only the ones written by the owner that have no reactions.  Anything with engagement is kept.
Uses the GitHub CLI (`gh`) as the logged-in account, which must own the repository.
"""
import json, subprocess, sys, time, os, re
from common import *

repo = sys.argv[1]; dry = "--dry-run" in sys.argv; migrate = "--migrate" in sys.argv
site = sys.argv[sys.argv.index("--site-url") + 1] if "--site-url" in sys.argv else ""
owner = repo.split("/")[0]
data = json.load(open(os.path.join(ROOT, "site-data", "concerns.json")))
VOTABLE = lambda c: c["level"] in ("high", "notable") and c["source"] != "NOT KNOWABLE"


def gh(*args, body=None):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, input=body)
    if r.returncode: sys.exit("gh failed: %s\n%s" % (" ".join(args[:4]), r.stderr.strip()))
    return json.loads(r.stdout) if r.stdout.strip() else None


def post(path, payload, method="POST"):
    if dry: return {"number": 0, "html_url": "(dry run)"}
    time.sleep(1.5)                                   # stay clear of GitHub's secondary rate limits
    return gh("-X", method, path, "--input", "-", body=json.dumps(payload))


def pages(path):
    out = []
    for p in range(1, 10):
        j = gh("%s%sper_page=100&page=%d" % (path, "&" if "?" in path else "?", p)) or []
        out += j
        if len(j) < 100: break
    return out


LABELS = {"direction": ("0b6bcb", "A hypothetical direction for a future OpenCL version"), "concern": ("a85d00", "A concern raised by a direction"), "high": ("b3261e", "High-level concern"), "notable": ("e0a24a", "Notable concern")}
have = {l["name"] for l in pages("repos/%s/labels" % repo)}
for name, (color, desc) in LABELS.items():
    if name not in have: post("repos/%s/labels" % repo, {"name": name, "color": color, "description": desc}); print("label", name)

existing = pages("repos/%s/issues?state=all" % repo)
by_marker = {}
for i in existing:
    if i.get("pull_request"): continue
    for kind in ("direction", "item"):
        m = re.search(r"<!-- vote-%s: ([\w-]+) -->" % kind, i.get("body") or "")
        if m: by_marker[(kind, m.group(1))] = i
made_d = made_c = 0


def direction_body(d, concern_list=""):
    return ("<!-- vote-direction: %s -->\n**%s**\n\n%s\n\nThis is a hypothetical direction for a future OpenCL version, produced by an independent tool from Khronos's public files. It is not a Khronos plan.\n\n"
            "**React to this post** to vote on the direction: 👍 = I would want this explored for a future version, 👎 = I would not. **Comment** to say why.\n\n"
            "Each concern raised by this direction is its own issue (listed below): react there to say whether you agree it is a real concern, and reply to discuss it. "
            "Your GitHub name is shown with your reply on the vote page%s. Informal and unweighted; one reaction per person.%s") % (d["id"], d["title"], d.get("intent") or "", (": " + site + "vote.html") if site else "", concern_list)

for d in data["directions"]:
    di = by_marker.get(("direction", d["id"]))
    if not di:
        di = post("repos/%s/issues" % repo, {"title": "Direction: " + d["title"], "body": direction_body(d), "labels": ["direction"]}); made_d += 1
        print("direction #%-3s %s" % (di["number"], d["title"]))
    created = []
    for c in [x for x in d["concerns"] if VOTABLE(x)]:
        ci = by_marker.get(("item", c["id"]))
        if not ci:
            short = re.sub(r"\s+", " ", c["text"])[:80].rstrip() + ("…" if len(c["text"]) > 80 else "")
            body = ("<!-- vote-item: %s -->\n**%s** · %s · direction: **%s**%s\n\n%s\n\n---\n"
                    "👍 = I agree this is a real concern for this direction. 👎 = I don't think so, or I think it is wrong (please reply with why).\n"
                    "Reply below to discuss; your GitHub name is shown with your reply on the vote page%s.\n\nID: `%s`") % (c["id"], c["level"], c["source"].lower(), d["title"], (" (#%s)" % di["number"]) if di["number"] else "", c["text"], (" (" + site + "vote.html)") if site else "", c["id"])
            ci = post("repos/%s/issues" % repo, {"title": "Concern: %s: %s" % (d["title"], short), "body": body, "labels": ["concern", c["level"]]}); made_c += 1
        created.append((ci, c))
    if di["number"] and "<!-- vote-concerns -->" not in (di.get("body") or ""):
        lst = "\n".join("- #%s (%s)" % (ci["number"], c["level"]) for ci, c in created if ci["number"]) or "_This direction raised no concern that is voted on; its facts are on the explorer's Concerns tab._"
        post("repos/%s/issues/%d" % (repo, di["number"]), {"body": direction_body(d, "\n\n<!-- vote-concerns -->\n**Concerns for this direction**\n" + lst), "labels": ["direction"]}, method="PATCH")

deleted = 0
if migrate:
    for c in pages("repos/%s/issues/comments" % repo):
        if c["user"]["login"] == owner and re.search(r"<!-- vote-item: ([\w-]+) -->", c.get("body") or "") and c["reactions"]["total_count"] == 0:
            if not dry:
                time.sleep(0.5); subprocess.run(["gh", "api", "-X", "DELETE", "repos/%s/issues/comments/%d" % (repo, c["id"])], check=True, capture_output=True)
            deleted += 1
print("%s: %d direction issue(s), %d concern issue(s) %s; %d legacy comment(s) %s" % ("dry run" if dry else "done", made_d, made_c, "would be created" if dry else "created", deleted, "would be deleted" if dry else "deleted"))
