#!/bin/sh
# Rebuild everything from the bare clones in ../sources.  Each step asserts its own controls.
# To pull new upstream commits first:  git --git-dir=sources/OpenCL-Docs.git fetch --tags origin '+refs/heads/*:refs/heads/*'  (same for Headers)
set -e
cd "$(dirname "$0")"
[ -d ../sources/OpenCL-Docs.git ] && [ -d ../sources/OpenCL-Headers.git ] || { echo "sources/ is missing: run ./fetch.sh first"; exit 1; }
python3 extract_registry.py   | tail -2
python3 extract_structure.py  | tail -4
python3 extract_changes.py    | tail -3
python3 extract_optional.py   | tail -3
python3 extract_headers.py    | tail -2
python3 extract_touchpoints.py| tail -2
python3 build_model.py        | tail -3     # pass 1: data only (the workbench reads it)
python3 workbench.py run      | tail -9
for n in ok bad-dangling bad-range-clash bad-gating bad-revision; do python3 workbench.py proposal demo-$n proposals/example-$n.patch "Example proposal: $n" >/dev/null; done
python3 workbench.py proposal demo-sheet-ok  proposals/example-ok.patch --sheet proposals/example-ok.sheet.json  "Example: good feature sheet" >/dev/null
python3 workbench.py proposal demo-sheet-bad proposals/example-ok.patch --sheet proposals/example-bad.sheet.json "Example: bad feature sheet" >/dev/null
python3 workbench.py proposal control-noop ref:main "CONTROL: main against itself (must change nothing)" >/dev/null
python3 workbench.py selftest | tail -7
python3 concerns.py           | head -1
mkdir -p ../site-data && cp ../workbench/results/concerns.json ../site-data/concerns.json
python3 workbench.py wizard proposals/example-wizard.json | tail -2
python3 build_model.py        | tail -4     # pass 2: now embeds the stored results
python3 build_viewer.py
if command -v chromium >/dev/null 2>&1; then python3 test_viewer.py | tail -1; else echo 'viewer test skipped (chromium not installed)'; fi
python3 build_site.py
if command -v chromium >/dev/null 2>&1; then python3 test_site.py | tail -1; else echo 'site test skipped (chromium not installed)'; fi
