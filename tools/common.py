"""Shared helpers for the OpenCL study tools. Stdlib only.

Every number the tools print or store is re-derived from the bare clones in
../sources, never typed in.  Each generator stamps the commit it read.
"""
import os, re, subprocess, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "sources", "OpenCL-Docs.git")
HDRS = os.path.join(ROOT, "sources", "OpenCL-Headers.git")
DATA = os.path.join(ROOT, "data")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "--git-dir=" + repo, *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def show(repo, ref, path):
    """File content at ref, or None if the path does not exist there."""
    r = subprocess.run(["git", "--git-dir=" + repo, "show", "%s:%s" % (ref, path)],
                       capture_output=True)
    if r.returncode:
        return None
    return r.stdout.decode("utf-8", "replace")


def ls_tree(repo, ref, path=""):
    args = ["ls-tree", "-r", "--name-only", ref] + ([path] if path else [])
    out = git(repo, *args, check=False)
    return [l for l in out.splitlines() if l]


def docs_tags():
    """Tags that carry xml/cl.xml, oldest first by commit date."""
    names = git(DOCS, "tag").split()
    rows = []
    for t in names:
        if not re.match(r"^v3\.\d+\.\d+", t):
            continue
        if show(DOCS, t, "xml/cl.xml") is None:
            continue
        date, sha = git(DOCS, "log", "-1", "--format=%cs %H", t).split()
        rows.append({"tag": t, "date": date, "commit": sha})
    rows.sort(key=lambda r: (r["date"], r["tag"]))
    return rows


def vkey(v):
    return tuple(int(x) for x in v.split("."))
