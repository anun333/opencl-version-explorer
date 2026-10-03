<!-- MAP
state: living
claim: Append-only list of mistakes made while extracting OpenCL version structure, written as mechanisms so they are not repeated.
-->
# Traps (append-only; amend an entry only when a later measurement overturns it)

1. **Empty listing helper.** `git ls-tree -r --name-only <tag> ""` returns nothing (not an error) when the path argument is the empty string. Every "extension chapter file" check came back negative until a control asked for a file known to exist. *Fix:* omit the argument when empty. (tools/common.py)

2. **A filter written for one file silently hid real symbols.** A prefix skip-list meant to drop internal macros in `cl_platform.h` also dropped `CL_DEVICE_TYPE_*`, `CL_MEM_*`, `CL_FP_*`, `CL_QUEUE_*`: 151 registry symbols reported "missing from the headers". The aggregate count of found symbols stayed healthy. *Detection:* print the names of the missing ones and read them. *Fix:* skip only the named internals.

3. **`#define X (1 << 0)` is not a function-like macro.** The pattern `(?!\s*\()` rejected every constant whose value starts with a parenthesis. A function-like macro has `(` *immediately* after the name. (tools/extract_headers.py)

4. **A skip rule for `CL_VERSION_` hid `CL_VERSION_MAJOR_BITS`.** Guard macros (`CL_VERSION_3_1`) are not API; version-encoding constants are. Match `CL_VERSION_\d_\d` exactly.

5. **Keyword heuristic missed an underscore spelling.** "device-side enqueue" did not match `DEVICE_SIDE_ENQUEUE`, so command-buffer showed no device-enqueue interaction. Heuristic keyword counts are labelled heuristic in the viewer for this reason; check the spelling variants of any keyword before reading a zero.

6. **A parser threshold I guessed was wrong, not the parser.** The check "API outline has more than 500 headings" failed at 220. An independent `grep -c` over the same files also gave 220. When a control fires, count the same thing a second way before touching the parser.

7. **Heading paths collide across chapters.** "Pipes" is a heading in both the runtime layer and appendix H. Key headings by (spec, path, file).

8. **Appendix titles use a single `=`; chapters use `==`.** Nest by the real `=` count with a stack, not by assumed depth.

9. **`||=` on a function call is a syntax error** (`(map.get(k) ||= []).push(...)`). It killed the whole viewer script, and an error listener registered after the script ran saw nothing. Register error listeners first (tools/test_viewer.py does).

10. **Snap Chromium cannot read `/tmp`.** `--dump-dom file:///tmp/x.html` returns Chromium's own "file not found" page, which has a plausible DOM length. Test pages must live under the home directory.

11. **A "bare ext name" bullet is sometimes content, sometimes a header.** `cl_khr_subgroup_rotate:` is a header; `cl_khr_unified_svm (experimental)` under "Added new extensions" is the change itself. Drop a bare bullet only if child bullets follow it. A control (unified_svm added in 3.1) caught the first attempt.

12. **Deprecation lives in three places and none is complete.** Registry require-block comments, command `prefix/suffix` attributes in `cl.xml`, and `/* deprecated */` comments in headers. `CL_DEVICE_HOST_UNIFIED_MEMORY` is deprecated since 2.0 (appendix E), flagged only in the 3.0 header, and un-deprecated in 3.1; the registry never flags it. Absence from the registry's deprecation lists proves nothing.

13. **Registry and headers disagree in four places** (reported, not hidden, in the viewer's Provenance tab): `CL_KHRONOS_VENDOR_ID_POCL` is in `cl.xml` but in no header; the three `CL_VERSION_*_BITS` macros are registry 3.0 but unguarded in 3.1 headers.

14. **Filename is not content.** The registry served `OpenCL_Ext.pdf` byte-identical to `OpenCL_API.pdf` (same md5, 672 pages). Hash downloads before trusting the name.

15. **Header tags trail header `main`.** OpenCL-Headers `main` (2026-09-30) is newer than the last tag `v2026.05.29` and already carries command-buffer extension version 1.0. `opencl-3.1/OpenCL-Headers/` in this folder is the *tag*, not `main`. The explorer reads `main`.

16. **Churn counts are mostly copyright years.** v3.0.19 → v3.1.0 touched 143 extension-spec files; 103 changed by two lines or fewer. Read area churn together with the "trivial" column.

17. **"Required in 3.1" is not in appendix H.** Appendix H is byte-identical at v3.0.19 and v3.1.2. 3.1's sub-group and SPIR-V requirements are written in the architecture chapter's version list, in query descriptions, and in the platform-layer extension-name list. A reader who greps appendix H for the 3.1 change finds nothing.

18. **My earlier guide said the registry covers 27 tags; it covers 22** (`xml/cl.xml` first exists at `v3.0.1-Provisional`; older tags have none). The viewer prints the real count.

19. **Identical macro redefinition is legal C.** The "re-promote something already in core" control did not fail to compile: `#define CL_DEVICE_UUID 0x106A` twice with the same value is allowed. The harness caught it through two other checks (the symbol is already visible at target 310; the stripped name already exists in the registry). A control's expected failure must be predicted from what the compiler actually rejects, and the scenario file records which check is expected to fire. (tools/scenarios/c01-*.json)

20. **A lazy `typedef ... NAME;` regex spans earlier structs.** With DOTALL and `.*?`, finding the typedef for the second struct returned the first struct plus the second, so the synthetic header defined a struct twice. Scan statement by statement (balanced braces to the `;`) and index by declared name. (tools/workbench.py)

21. **A promoted struct needs its tag renamed too.** Renaming only the typedef (`cl_x_khr` to `cl_x`) leaves `struct _cl_x_khr` defined in both `cl.h` and `cl_ext.h`. The real 3.1 header renames the tag (`_cl_device_integer_dot_product_acceleration_properties`). Consequence for any promotion with a struct: the core and extension types are then distinct, not aliases.

22. **A promoted command adds three header edits, not one.** `cl.h` prototype, `cl_function_types.h` typedefs, and an entry at the *end* of `cl_icd.h`'s `cl_icd_dispatch` struct, with a `void *` placeholder in the `#else` so the struct layout is the same at every target version. The harness checks that existing field offsets do not move and that size grows by exactly one pointer per command.

23. **A must-fail test can fail for the wrong reason.** The "symbols are not visible at 310" check only means something because the same program compiles at 320; keep the two together and show the first `error:` line, not the first line of output.

24. **Glob deletions are blocked by the harness safety check.** Results are overwritten per scenario and `log.jsonl` is append-only, so nothing needed deleting.

25. **A registry rule must be run on the untouched baseline before it is believed.** I wrote "each enum value must lie inside the start/end of its `<enums>` block". In the baseline v3.1.2 registry 312 of 726 existing enums already violate it (a block's range is a reservation; enums of other groups follow it). My own bad example looked caught; real in-flight branches were being flagged for nothing. The rule is removed. Any new check is only reported for problems the *proposal* introduces, and a check that fires on the baseline is not a check.

26. **A branch's registry is stale relative to current headers.** Generating headers from a branch's whole `cl.xml` and compiling them against newer core headers produced errors (`cl_icd.h` wanting a 3.1 typedef the branch's `cl_function_types.h` lacked) that belong to neither the proposal nor the headers. Test a branch by merging only its own change (merge-base to branch tip) onto current main, with `git merge-file`; report conflicts instead of guessing.

27. **`git diff --no-index` writes `a/a/...` paths.** Patches built that way do not apply with `git apply`; the tester caught it ("No such file").

28. **The header generator exits 0 after raising an exception.** On an `<extension>` with no `revision` it prints a `TypeError` traceback and still returns success, leaving the header without that extension. "generator/runs: ok" was true for the exit code and false for the work. Its error text is Mako's (`: error in render_body`, `TypeError:`), with no word "Traceback"; my first detector looked for that word and missed it. Check exit code, an error-text pattern, and that the set of generated files equals the baseline's. (Found on a real in-flight branch, then reproduced on its raw, unmerged registry.)

29. **Do not turn a convention you assumed into a failing check.** I made "symbols must be hidden below the extension's declared version" a FAIL; 19 of the 21 released extensions with a version dependency declare no `condition` and are visible on older targets. The check is now a FAIL only when the extension's own declared `condition` contradicts its `depends`, and otherwise reports the baseline counts as information.

30. **Verify a finding on the raw input before attributing it, then confirm the diagnosis by changing one thing.** A proposal's generated header failed to compile because a structure appeared before the type it uses. I first said the *generator* emits structures first, because in the registry's `<types>` section the typedef comes first. That was wrong: the header is emitted in the order of names in the extension's `<require>` list, and the proposal listed the structure before the typedef. A probe settled it: the same proposal compiles with the typedef listed first and fails with the structure listed first. Now checked at registry level by `registry/type-order`, and the wizard orders types itself.

31. **The optional-feature contract check was validated before being trusted.** Its query rule (a detection query exists, sits in an `*_info` group, and is required by the extension) was run over every released extension that exposes a device or platform query: 15 of 15 pass. The macro-collision rule checks against the 22 `__opencl_c_*` names found in the specs. Its absent-behaviour rule has no baseline to validate against (appendix H is prose tables, not data), so it reports what the sheet declares and nothing about whether the behaviour is *good*.

32. **`clinfo`'s text view can mislead; use `--raw` for the value.** The default output printed `Shared Virtual Memory (SVM) capabilities (core)` with an empty value and a separate `SVM 0 bytes` line, which I read as "no SVM" and repeated in the guide. `clinfo --raw` shows `CL_DEVICE_SVM_CAPABILITIES = CL_DEVICE_SVM_COARSE_GRAIN_BUFFER`. A label ("SVM 0 bytes") was standing in for the thing (the capability bitfield). Corrected in the guide.

33. **A results folder collects more than one kind of JSON.** After `concerns.json` and `calibration-3.1.json` were added next to the run results, two readers that took "every .json here" crashed with `KeyError`. It did not show on the first run because the order of steps wrote the new file after the readers had finished. Readers now accept a file only if it has the keys of a run result, and the pipeline was re-run twice in a row to catch exactly this.

34. **"Changes from vX" means the release AFTER X.** The 3.0-era appendix headings read `Changes from *v3.0.16*:` and list what shipped in 3.0.17 (the 3.1 appendix relabels them `v3.0.16 to v3.0.17`). The study guide cited five items one release too early. Corrected against the extracted `from`/`to` fields, which already normalise this; the extractor was right and my prose was not.

35. **Listeners added to a persistent container stack up.** The Propose tab first attached its click and input handlers to the page's `main` element, which survives tab changes; each visit added another set, so one click would add several rows. Attach to a wrapper created fresh on each render; a test visits the tab twice and clicks once.

36. **An acronym alias must be matched by its own spelling, not the term's.** The glossary underlines "SVM" only when written in capitals, but its alias "shared virtual memory" is lower case; keying the case rule on the term skipped the alias. Decide case-sensitivity per alias.

37. **Backslashes in a JavaScript test written inside a Python string.** `\s`, `\b` and `\.` need doubling; a single `\b` silently becomes a backspace character and changes the regex. Build the test script, then run `python -W error` over it.

38. **`pkill -f` can kill the shell that runs it.** The pattern appeared in my own command line. Test servers are now started and stopped inside a Python script on a free port (`tools/test_site.py`), not with background shell jobs and signal commands.

39. **A hosted page needs things a local file never asks for.** Over HTTP the browser requested `/favicon.ico` and got a 404; the page now carries an inline icon. The site test serves the folder as a real host would and opens deep links.

40. **Header order follows the `<require>` list, not the definition order.** In a registry extension entry, list typedefs before the structures that use them. The generator will not reorder them and the header will not compile. (Seen on a real in-flight proposal; reproduced with a probe; caught by `registry/type-order`.)

41. **Two labelling schemes for one release.** Changelog entries for the 3.0 to 3.1 summary are labelled `OpenCL 3.1`, but the Compare view filtered by spec tags (`v3.1.0`), so the range v3.0.19 to v3.1.0 showed 0 changelog entries even though the summary exists. Found by checking a number the tour printed against the view next to it. `OpenCL 3.1` is now mapped to `v3.1.0`, and a test asserts that the 3.1 summary appears in that comparison.

42. **A DOM dump includes script source.** Searching a dumped page for an error message matched the message inside the page's own JavaScript, so a check meant to fail on an error banner could never fail, and a live check reported an error that was not there. Search only text a person sees (scripts and styles removed) and read the specific status element. The same flaw would have hidden a real failure in the site test.

43. **GitHub issue comments are flat.** A reply cannot attach to a particular earlier comment, so putting each concern as a comment on a direction issue made per-concern discussion impossible. Each concern is now its own issue; replies thread under it naturally and votes are reactions on the issue. IDs are unchanged, so nothing was lost by migrating (nothing had been voted on yet; the migration only deletes the owner's own seeded comments that have no reactions).

44. **GitHub's label filter lags edits.** Immediately after patching two issues, listing by label still returned 12 of 14. The check was repeated a few seconds later; read an edited item back directly before concluding an edit failed.

45. **A test's fake server can answer for the thing it is checking.** The "voting is off" check reported `config.json` and `hidden.json` as still served, because the test's own fake GitHub API answered those two paths regardless of what the site contained. The fake routes now exist only in voting mode, and the absence checks run against the real site folder. Also: switching a feature off should leave an assertion behind (the build refuses to embed appendix H wording; the site test fails if a vote file is served).

46. **`git apply` inside a repository silently applies nothing.** Once the package folder became a git repository, every patch-based test passed vacuously (no failures, no symbols) because `git apply` skips patch paths that do not match the repository layout and still exits 0. It showed only in a fresh copy of the package, never in the workspace, which was not a repo. The tester now hides the enclosing repository from git, refuses a patch that changes nothing, and the self-test applies a patch from inside a throwaway repo. Lesson: after turning a folder into a repository, run the whole pipeline from a fresh copy of it.
