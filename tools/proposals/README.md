# Example proposals (not real)

These patch `xml/cl.xml` at v3.1.2 with an invented vendor extension (`cl_zzdemo_optional_query`) to show what the proposal tester catches.
They are demonstrations, not Khronos proposals. Run, e.g.:

    python3 tools/workbench.py proposal demo-ok tools/proposals/example-ok.patch

- `example-ok` should pass everything.
- `example-bad-dangling` requires a command that is not defined.
- `example-bad-range-clash` reuses an existing enum value in the same group. A compiler cannot see this (two macros may share a value); only the registry check does.
- `example-bad-gating` declares `depends` on OpenCL 3.0 but a `condition` for 1.2, contradicting itself; the compile test sees the symbols on a 2.2 target. (Omitting `condition` entirely is *not* flagged: 19 of 21 released extensions with a version dependency do that.)
- `example-bad-revision` has no `revision` attribute. The header generator then raises an error but still exits 0; the tester reads the output, not just the exit code.

To test your own change: edit `xml/cl.xml` in a checkout of OpenCL-Docs, `git diff > my.patch`, then pass the patch file. Or, for a branch in the cloned docs repo: `... proposal my-id ref:<branch>`.

## Feature sheets (optional-feature proposals)

Add `--sheet my.sheet.json` to also check the OpenCL 3.0 optional-feature pairing: a detection query, an OpenCL C feature macro, and what each new command returns when the feature is absent.

    {"feature": "Demo optional query", "extension": "cl_zzdemo_optional_query",
     "queries": ["CL_DEVICE_DEMO_QUERY_ZZDEMO"], "macros": ["__opencl_c_zzdemo"],
     "absent": {"clGetDemoInfoZZDEMO": "CL_INVALID_OPERATION"}}

The report then includes a draft appendix-H section in the existing table format. It is a starting point for the author, not spec text. `example-bad.sheet.json` shows the three mistakes it catches.

## Structure types

A wizard spec may describe a structure instead of a whole-number type: give `"members": ["cl_uint count", "cl_bool supported"]` and no `"base"`. See `example-wizard-struct.json`. The wizard puts whole-number types first and structures after any structure they use, so the order you list them in does not matter (`example-wizard-struct-order.json` lists a structure before the type it uses on purpose). In a registry patch written by hand the order of names in the extension's `<require>` list is yours to get right: `example-bad-type-order.patch` shows the mistake, which the `registry/type-order` check names directly and which otherwise surfaces only as a compile error in the generated header.
