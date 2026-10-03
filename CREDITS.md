# Credits and licences of the data

This tool is independent. It is not affiliated with, endorsed by, or reviewed by The Khronos Group. The tool's own code and documentation are Apache-2.0 (`LICENSE`), copyright 2026 anun333; this file concerns the Khronos-derived data it reads and embeds.

## Sources (read at run time from the public repositories; the repositories themselves are not redistributed here)

| Source | What is used | Licence stated by the source |
|---|---|---|
| `KhronosGroup/OpenCL-Docs`, `xml/cl.xml` | symbol names, extension names, revisions, dependencies, promotion and deprecation metadata | Apache License 2.0 (stated in the file) |
| `KhronosGroup/OpenCL-Docs`, `api/appendix_e.asciidoc`, `api/opencl_architecture.asciidoc`, `api/opencl_platform_layer.asciidoc` | changelog sentences, requirement statements, counts of words | CC BY 4.0 (`SPDX-License-Identifier` in each file) |
| `KhronosGroup/OpenCL-Docs`, `c/appendix_a.asciidoc` | OpenCL C changelog sentences | CC BY 4.0 (stated in the file) |
| `KhronosGroup/OpenCL-Docs`, `api/appendix_h.asciidoc` | the optional-feature tables and prose shown in the *Optional features* tab, lightly reformatted (see the note below) | CC BY 4.0 by the repository's general statement. The file has a copyright line but no licence header of its own: see the note below. |
| `KhronosGroup/OpenCL-Docs`, extension chapters (`api/cl_*.asciidoc`) | word counts and keyword counts only (no text is embedded) | CC BY 4.0 |
| `KhronosGroup/OpenCL-Headers` | symbol lists and guards; the headers are compiled locally and modified copies are generated in a scratch folder | Apache License 2.0 |
| `KhronosGroup/OpenCL-Headers`, `scripts/` (header generator) | run unmodified by the proposal tester | Apache License 2.0 |

Copyright of the sources is held by The Khronos Group Inc. (and, for some files, other contributors named in the files).

## Changes made

The data is extracted, restructured, joined across versions, and in places summarised or classified by keyword. Quoted changelog sentences are verbatim except that markup was removed and cross-reference macros were rewritten as plain text. Where the page shows a derived figure it says so.

## Note on appendix H

`api/appendix_h.asciidoc` has a copyright line (The Khronos Group Inc.) but, unlike 119 of the 122 specification source files in `api/`, `c/` and `env/`, no licence header of its own (the other two are `c/features.txt` and `c/functions.txt`). The repository's `LICENSE` states that "the asciidoctor sources for the OpenCL Specifications and other documention are under the Creative Commons Attribution 4.0 International (CC BY 4.0) license", and its README says the same of the specification source files. This tool therefore shows appendix H's tables and prose under CC BY 4.0, with attribution on the *Optional features* tab: the copyright holder, a link to the source file at the commit used, a link to the licence, a statement that Khronos does not endorse the page, and the changes made.

**Changes made to the text:** asciidoc markup was removed (emphasis underscores, inline-code backticks, escaped pipes, line-break markers), source comments (lines starting `//`, which are not part of the published text) were dropped, cross-reference macros such as `{clGetDeviceInfo}` were replaced by the plain name, and whitespace was collapsed. The wording is otherwise unchanged.

If Khronos objects, or you prefer to be cautious, build with `WITHHOLD_APPENDIX_H=1` (see `tools/build_viewer.py`): the page then shows only names, counts and a link to the specification.

## Trademarks

OpenCL is a trademark of Apple Inc. used under license by Khronos. Khronos is a registered trademark of The Khronos Group Inc. Other names are used solely for identification and belong to their owners.

## AI assistance

The code, the study guide and these documents were produced with AI assistance and edited and directed by a person. Anyone contributing the tool's output to Khronos should read the AI-assisted-contribution statements in the contribution guidelines of the repositories concerned.
