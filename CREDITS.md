# Credits and licences of the data

This tool is independent. It is not affiliated with, endorsed by, or reviewed by The Khronos Group. The tool's own code and documentation are Apache-2.0 (`LICENSE`), copyright 2026 anun333; this file concerns the Khronos-derived data it reads and embeds.

## Sources (read at run time from the public repositories; the repositories themselves are not redistributed here)

| Source | What is used | Licence stated by the source |
|---|---|---|
| `KhronosGroup/OpenCL-Docs`, `xml/cl.xml` | symbol names, extension names, revisions, dependencies, promotion and deprecation metadata | Apache License 2.0 (stated in the file) |
| `KhronosGroup/OpenCL-Docs`, `api/appendix_e.asciidoc`, `api/opencl_architecture.asciidoc`, `api/opencl_platform_layer.asciidoc` | changelog sentences, requirement statements, counts of words | CC BY 4.0 (`SPDX-License-Identifier` in each file) |
| `KhronosGroup/OpenCL-Docs`, `c/appendix_a.asciidoc` | OpenCL C changelog sentences | CC BY 4.0 (stated in the file) |
| `KhronosGroup/OpenCL-Docs`, `api/appendix_h.asciidoc` | read at build time for names (functions, queries, feature macros) and counts of table rows; **its wording is not embedded or redistributed** | The file carries a copyright line but no licence statement, which is why the wording is withheld. |
| `KhronosGroup/OpenCL-Docs`, extension chapters (`api/cl_*.asciidoc`) | word counts and keyword counts only (no text is embedded) | CC BY 4.0 |
| `KhronosGroup/OpenCL-Headers` | symbol lists and guards; the headers are compiled locally and modified copies are generated in a scratch folder | Apache License 2.0 |
| `KhronosGroup/OpenCL-Headers`, `scripts/` (header generator) | run unmodified by the proposal tester | Apache License 2.0 |

Copyright of the sources is held by The Khronos Group Inc. (and, for some files, other contributors named in the files).

## Changes made

The data is extracted, restructured, joined across versions, and in places summarised or classified by keyword. Quoted changelog sentences are verbatim except that markup was removed and cross-reference macros were rewritten as plain text. Where the page shows a derived figure it says so.

## Note on appendix H

Because `appendix_h.asciidoc` states no licence, the page does not embed its tables or prose. It shows names and counts derived from it and links to the specification for the wording. `tools/build_viewer.py` fails the build if known appendix H sentences appear in the page.

## Trademarks

OpenCL is a trademark of Apple Inc. used under license by Khronos. Khronos is a registered trademark of The Khronos Group Inc. Other names are used solely for identification and belong to their owners.

## AI assistance

The code, the study guide and these documents were produced with AI assistance and edited and directed by a person. Anyone contributing the tool's output to Khronos should read the AI-assisted-contribution statements in the contribution guidelines of the repositories concerned.
