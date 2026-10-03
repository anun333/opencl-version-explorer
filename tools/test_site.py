#!/usr/bin/env python3
"""Serve site/ over HTTP on a free port, open a deep link in headless Chromium, check the page restores the view.

This is what a static host (GitHub Pages) does, so it catches problems that file:// hides (paths, hash routing).
"""
import functools, http.server, json, os, re, subprocess, sys, threading, html, urllib.parse, urllib.request
from common import ROOT

voting = "--with-voting" in sys.argv
site = os.path.join(ROOT, "site")
assert os.path.exists(os.path.join(site, "index.html")), "run tools/build_site.py first"
CONC = json.load(open(os.path.join(site if voting else os.path.join(ROOT, "site-data"), "concerns.json")))
D0 = CONC["directions"][0]
ITEM = next(c for c in D0["concerns"] if c["level"] in ("high", "notable") and c["source"] != "NOT KNOWABLE")
OTHER = next(c for d in CONC["directions"][1:] for c in d["concerns"] if c["level"] in ("high", "notable") and c["source"] != "NOT KNOWABLE")


class Quiet(http.server.SimpleHTTPRequestHandler):
    """Serves site/ and a fake GitHub API at /api (a vote item, a direction, and a spoofed comment from another user)."""
    def log_message(self, *a, **k): pass
    def _json(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if voting and u.path == "/config.json": return self._json(200, {"repo": "owner/repo"})
        if voting and u.path == "/hidden.json": return self._json(200, {"comments": [777]})
        if u.path.startswith("/fail/"): return self._json(403, {"message": "rate limited"})
        if u.path.startswith("/api/"):
            page = int(urllib.parse.parse_qs(u.query).get("page", ["1"])[0])
            if page > 1: return self._json(200, [])
            if u.path.endswith("/issues"):
                return self._json(200, [
                    {"number": 1, "html_url": "https://github.com/owner/repo/issues/1", "user": {"login": "owner"}, "body": "<!-- vote-direction: %s -->" % D0["id"], "reactions": {"+1": 3, "-1": 1}},
                    {"number": 2, "html_url": "https://github.com/owner/repo/issues/2", "user": {"login": "owner"}, "body": "<!-- vote-item: %s -->" % ITEM["id"], "reactions": {"+1": 5, "-1": 0}},
                    {"number": 3, "html_url": "https://github.com/owner/repo/issues/3", "user": {"login": "someone-else"}, "body": "<!-- vote-item: %s -->" % OTHER["id"], "reactions": {"+1": 99, "-1": 0}}])
            if u.path.endswith("/issues/comments"):
                mk = lambda cid, n, login, body: {"id": cid, "issue_url": "https://api.github.com/repos/owner/repo/issues/%d" % n, "html_url": "https://github.com/owner/repo/issues/%d#issuecomment-%d" % (n, cid), "user": {"login": login}, "body": body, "created_at": "2026-10-03T12:00:00Z"}
                return self._json(200, [mk(101, 2, "alice-the-reviewer", "I disagree because the ratified label matters."), mk(777, 2, "troll-account", "HIDDEN-BY-OWNER-TEXT"),
                                        mk(102, 1, "bob-the-implementer", "We would want this explored."), mk(103, 3, "someone-else", "reply on a spoofed issue")])
        return super().do_GET()
Handler = functools.partial(Quiet, directory=site)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
checks = {"compare": ("#compare?ca=v3.0.19&cb=v3.1.0", "v3.0.19 → v3.1.0"),
          "extensions": ("#extensions?ext=cl_khr_unified_svm", "cl_khr_unified_svm"),
          "help": ("#help", "Start here"),
          "propose": ("#propose", "Checks you can see right now")}
bad = []
def visible(dom): return re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", "", dom, flags=re.S))      # text a person sees, never script source
def status(dom):
    m = re.search(r'<span id="status"[^>]*>(.*?)</span>', dom, re.S); return m.group(1) if m else ""
def dump(url): return subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=6000", "--dump-dom", url], capture_output=True, text=True, timeout=120).stdout
try:
    base = "http://127.0.0.1:%d" % port
    if voting:
        # the vote page against the fake API: real counts shown, a spoofed comment from another user ignored, failure handled
        page = dump(base + "/vote.html?api=" + urllib.parse.quote(base + "/api", safe="")); txt = visible(page)
        good = ("+5" in txt) and ("+2" in txt) and ("+99" not in txt) and "Outcomes so far" in txt and "vote or reply on GitHub" in txt and "unavailable" not in status(page) and "Counts and replies" in status(page)
        good = good and "@alice-the-reviewer" in txt and "I disagree because the ratified label matters." in txt and "@bob-the-implementer" in txt     # replies shown with the author's GitHub name
        good = good and "HIDDEN-BY-OWNER-TEXT" not in txt and "troll-account" not in txt                                                            # moderation list honoured
        good = good and "reply on a spoofed issue" not in txt and ("ID " + ITEM["id"]) in txt                                                       # replies on a non-owner's issue ignored; IDs shown
        print("%-11s %s" % ("vote page", "ok" if good else "FAIL")); good or bad.append("vote page counts")
        fpage = dump(base + "/vote.html?api=" + urllib.parse.quote(base + "/fail", safe=""))
        good2 = "unavailable right now" in status(fpage) and D0["title"] in visible(fpage) and "Outcomes so far" not in visible(fpage)
        print("%-11s %s" % ("vote fail", "ok" if good2 else "FAIL")); good2 or bad.append("vote page failure mode")
    else:                                                          # voting is off: nothing from it may be served
        for f in ("vote.html", "config.json", "concerns.json", "hidden.json"):
            import urllib.error
            try: urllib.request.urlopen(base + "/" + f); code = 200
            except urllib.error.HTTPError as e: code = e.code
            print("%-11s %s" % (f, "absent (404) ok" if code == 404 else "FAIL: served (%s)" % code)); code == 404 or bad.append(f + " is still served")
        idx = dump(base + "/index.html#concerns")                  # the explorer must not link to a vote page that is not there
        nolink = bool(re.search(r'id="votelink"[^>]*\bhidden', idx)) and "Want to weigh in" not in visible(idx)
        print("%-11s %s" % ("vote links", "hidden ok" if nolink else "FAIL")); nolink or bad.append("vote link visible while voting is off")
    for name, (frag, needle) in checks.items():
        out = subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=5000", "--dump-dom", "http://127.0.0.1:%d/index.html%s" % (port, frag)],
                             capture_output=True, text=True, timeout=120).stdout
        ok = needle in out and "not affiliated" in out and len(out) > 20000
        print("%-11s %s (%d chars)" % (name, "ok" if ok else "FAIL", len(out)))
        if not ok: bad.append(name)
finally:
    srv.shutdown()
sys.exit("SITE TEST FAIL: " + ", ".join(bad)) if bad else print("site OK (served over http)")
