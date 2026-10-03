# OpenCL Version Explorer

An independent, local tool for seeing how the OpenCL specification changes from version to version, and for testing a hypothetical change before proposing it. It reads the public Khronos repositories (`OpenCL-Docs` and `OpenCL-Headers`). It is **not** affiliated with or endorsed by Khronos, and nothing it produces is a Khronos artifact.

Built with AI assistance. Every figure is recomputed by a script from the Khronos sources, and the scripts check themselves (see *How it avoids being wrong* below). It has not been reviewed by a member of the OpenCL working group; treat anything marked *heuristic* as a pointer for reading, not a verdict.

## Just look at it

New here? Open the page and start at **Start here** (it also has a 2-minute guided tour with live numbers): it explains the tool, every tab, and the terms. Words with a dotted underline explain themselves when clicked. The address bar always holds the whole view, so *Copy link to this view* sends exactly what you are looking at.

Open `opencl-explorer.html` in a browser. It is a single file with the data embedded; nothing is sent anywhere.

- **Overview / Versions / Compare**: core API size per version, deprecations, extension additions, removals, status changes, spec headings and API reference pages added or removed between any two spec tags, with the spec's own changelog entries.
- **Structure**: the spec outline (API, OpenCL C, SPIR-V environment) with the tags each heading appeared in, and each API function mapped to its spec section.
- **Extensions**: the lifecycle of every registry extension: status, dependencies, dependents, symbols.
- **Optional features**: the OpenCL 3.0 contract (appendix H): how to detect each optional feature and what each API does when it is absent.
- **3.2 workbench**: tick extensions to promote, or an optional feature to make required, and get the consequences that can be read from the sources, using what 3.0 to 3.1 did as the precedent. This is not a Khronos plan; no 3.2 exists in the repositories.
- **Concerns**: what each hypothetical 3.2 direction would raise (promote, require, deprecate), every line tagged tested, derived, heuristic, sample or not knowable.
- **Propose**: describe an extension you are considering in a form; it checks the description as you type and gives you a file to run the full test on your own machine (below).
- **Test results**: stored runs of the back end (below).

## Rebuild it or run your own tests

Needs `git` and Python 3 (tested with 3.12; the extractors use only the standard library). The test back end also needs `gcc`, `g++`, `xmllint` and Python's `mako` (on Debian/Ubuntu: `sudo apt install build-essential libxml2-utils python3-mako git`). Chromium is optional (a self-test of the page).

    ./fetch.sh            # downloads the two Khronos repos (about 11 MB) pinned to the commits in PIN
    ./tools/regen.sh      # extracts, tests, and rebuilds opencl-explorer.html

`./fetch.sh --latest` follows upstream instead of the pinned commits; results will then differ from the ones described here.

### Test a hypothetical OpenCL 3.2 promotion

Scenario files in `tools/scenarios/` name extensions to promote or an optional feature to require:

    python3 tools/workbench.py run                 # all scenarios; writes workbench/results/
    python3 tools/workbench.py compare s01-command-buffer s02-command-buffer-plus-mutable

For each scenario it builds a *synthetic* `CL_VERSION_3_2` header set from the real headers and compiles it with gcc and g++ at every target version, checks that symbols are hidden at older targets, that existing `cl_icd_dispatch` ABI offsets do not move, and that the registry stays consistent.

`tools/concerns.py` turns the stored results into `workbench/results/CONCERNS.md`: for each direction (promote a family of extensions, require an optional feature, deprecate something) the concerns it raises, each tagged TESTED, DERIVED, HEURISTIC, SAMPLE (one real device read with `clinfo --raw`, if available) or NOT KNOWABLE. It is evidence for a discussion, not a prediction.

### Describe a proposal in a form (no XML by hand)

Use the page's **Propose** tab, download `proposal.json`, then:

    python3 tools/workbench.py wizard proposal.json

The wizard turns the description into a patch to `xml/cl.xml` and a feature sheet, runs the full proposal test below, and writes `workbench/results/<id>.md` plus the patch you can attach to an issue.

### Test your own proposal

Express the change as an edit to `xml/cl.xml` (a patch, or a branch in the cloned `OpenCL-Docs`):

    python3 tools/workbench.py proposal my-id my.patch
    python3 tools/workbench.py proposal my-id my.patch --sheet my.sheet.json   # also checks the optional-feature contract
    python3 tools/workbench.py proposal my-id ref:some-branch                  # only that branch's own change, merged onto main

It applies the change, checks the registry (duplicates, unresolved references, enum value clashes, dependencies), regenerates the headers with Khronos's own generator, diffs the generated headers, and compiles them. A feature sheet adds the 3.0 pairing checks (detection query, OpenCL C feature macro, behaviour when absent) and drafts an appendix-H section. See `tools/proposals/README.md` for worked examples, including deliberately broken ones.

## How it avoids being wrong

- **Extracted, derived or heuristic** is labelled on every figure in the page.
- Every extractor asserts known positives in the same run, so an empty result cannot pass as "nothing there".
- `python3 tools/workbench.py selftest` proves the proposal tester still catches known-bad examples and passes a good one.
- `TRAPS.md` records each mistake made while building this, as a mechanism (about thirty so far). Several came from the tool's own checks failing; read it before changing an extractor.
- The 3.1 promotion rules are calibrated by replaying the real 3.0 to 3.1 promotions through them.

## Limits

It tests whether a change is *self-consistent* at the registry and header level. It does not read spec prose, check OpenCL C built-ins or semantics, run conformance tests, build the ICD loader, or know which implementations ship what. A proposal that passes here is consistent, not necessarily a good idea. The 3.2 workbench report is partly rule-based and partly keyword-based; the page says which.

## Hosting it

The explorer is one self-contained file, so any static host works. This repository publishes it with GitHub Pages (`.github/workflows/pages.yml`). `tools/build_site.py` prepares `site/`, `tools/test_site.py` checks it over HTTP, and `docs/publishing-to-github-pages.md` explains the pieces.

A companion voting page (votes as GitHub reactions on issues, replies as comments) was built and then taken down on 2026-10-03; it is off by default and the doc explains how to switch it back on.

The Optional features tab shows the tables and text of appendix H of the API specification, attributed under CC BY 4.0 (see `CREDITS.md` for the basis and the changes made); `WITHHOLD_APPENDIX_H=1` builds a page without the wording.

## Feedback

Corrections are welcome, especially from people who know the specification: please open an issue with the file, the claim, and what the source actually says.

## Licence and credits

The code and documentation are under the Apache License 2.0 (`LICENSE`, `NOTICE`), copyright 2026 anun333. The page embeds data derived from Khronos's repositories, which keeps its own licences: see `CREDITS.md`, including the note about appendix H.
