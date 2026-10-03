> **Generated with AI assistance and not reviewed by a Khronos member.** Facts are cited to files in the Khronos repositories; interpretation is marked. Section 5 uses one example machine.

# OpenCL 3.0 deep-dive, and what changed in 3.1 and onward

Written 2026-10-03. Sources: the copies in this folder (spec sources `v3.0.19` and `v3.1.2`,
headers `v2023.12.14` and `v2026.05.29`) plus `clinfo` on this machine.
Paths below are relative to this folder. "Source:" lines say where a claim comes from, so you can check it.
Anything marked **(background)** is general knowledge, not read from these files.

---------------------------------------------------------------------------------------------------

## 1. The big idea of OpenCL 3.0

OpenCL 2.x made a lot of features mandatory (SVM, generic address space, device-side enqueue, pipes,
the full C11-style atomics model...). Most vendors never shipped them, so many devices were stuck at 1.2.
**3.0 un-bundles that.** It is the 1.2 baseline plus a set of *optional* features that a device advertises
through queries (API) and feature macros (kernel language).

- 3.0 is "a major revision that breaks backwards compatibility" only in the sense that a 3.0 device
  need not implement what a 2.x device had to. Source: `opencl-3.0/OpenCL-Docs-src/api/appendix_e.asciidoc`
  ("Summary of Changes from OpenCL 2.2 to OpenCL 3.0") and `api/appendix_h.asciidoc`.
- A 1.2 application runs on 3.0 unchanged. A 2.x application must now *check* for what it uses.
- The first non-experimental 3.0 spec was v3.0.5. The line ran to v3.0.19, then 3.1.0.

### 1.1 The optional features (appendix H)
Each row: how to detect it in the API, and the kernel-language macro (OpenCL C 3.0).

| Feature | API detection | OpenCL C 3.0 macro |
|---|---|---|
| Shared Virtual Memory | `CL_DEVICE_SVM_CAPABILITIES` is 0 | none (API only) |
| Full atomics memory model (orders/scopes) | `CL_DEVICE_ATOMIC_MEMORY_CAPABILITIES`, `CL_DEVICE_ATOMIC_FENCE_CAPABILITIES` | `__opencl_c_atomic_order_acq_rel`, `_order_seq_cst`, `_scope_device`, `_scope_all_devices` |
| Device-side enqueue, on-device queues | `CL_DEVICE_DEVICE_ENQUEUE_CAPABILITIES` | `__opencl_c_device_enqueue` (requires generic address space and program-scope globals) |
| Pipes | `CL_DEVICE_PIPE_SUPPORT` | `__opencl_c_pipes` |
| Program-scope global variables | queried through feature list | `__opencl_c_program_scope_global_variables` |
| Non-uniform work-group sizes | `CL_DEVICE_NON_UNIFORM_WORK_GROUP_SUPPORT` | none |
| Read-write images | `CL_DEVICE_MAX_READ_WRITE_IMAGE_ARGS` is 0 | `__opencl_c_read_write_images` |
| 2D image from buffer, sRGB, depth images | image-format queries | extension-based |
| Device/host timer sync | `clGetHostTimer`, `clGetDeviceAndHostTimer` may fail | none |
| IL programs (SPIR-V) | `CL_DEVICE_ILS_WITH_VERSION` empty | none |
| Sub-groups | `CL_DEVICE_MAX_NUM_SUB_GROUPS` is 0 | `__opencl_c_subgroups` |
| 3D image writes | image-format queries | `__opencl_c_3d_image_writes` |
| Work-group collectives (broadcast, scan, reduce) | `CL_DEVICE_WORK_GROUP_COLLECTIVE_FUNCTIONS_SUPPORT` | `__opencl_c_work_group_collective_functions` |
| Generic address space | `CL_DEVICE_GENERIC_ADDRESS_SPACE_SUPPORT` | `__opencl_c_generic_address_space` |
| Already optional, now with macros | `images`, `double`, `long` | `__opencl_c_images`, `__opencl_c_fp64`, `__opencl_c_int64` |
| Program init/cleanup kernels (2.2) | **not supported in 3.0; APIs deprecated** | none |

When a feature is absent, appendix H gives the *exact* return value of each affected call
(e.g. `clSVMAlloc` returns NULL, `clEnqueueSVM*` returns `CL_INVALID_OPERATION`). That is the
"contract" a portable app codes against.

### 1.2 New 3.0 API surface (summary)
Source: appendix_e, 2.2-to-3.0 section.
- **Versioning queries:** `CL_PLATFORM_NUMERIC_VERSION`, `CL_DEVICE_NUMERIC_VERSION`,
  `*_EXTENSIONS_WITH_VERSION`, `CL_DEVICE_ILS_WITH_VERSION`, `CL_DEVICE_BUILT_IN_KERNELS_WITH_VERSION`.
  Versions are `cl_version` packed integers (10-bit major, 10-bit minor, 12-bit patch).
- **Feature queries:** `CL_DEVICE_OPENCL_C_ALL_VERSIONS`, `CL_DEVICE_OPENCL_C_FEATURES`,
  `CL_DEVICE_LATEST_CONFORMANCE_VERSION_PASSED`, `CL_DEVICE_PREFERRED_WORK_GROUP_SIZE_MULTIPLE`.
- **Properties-based creation:** `clCreateBufferWithProperties`, `clCreateImageWithProperties`
  (no properties defined in core, but a hook for extensions), and `CL_MEM_PROPERTIES`,
  `CL_PIPE_PROPERTIES`, `CL_SAMPLER_PROPERTIES`, `CL_QUEUE_PROPERTIES_ARRAY` queries.
- **`clSetContextDestructorCallback`** so apps can free user data tied to a context callback.
- `CL_COMMAND_SVM_MIGRATE_MEM` event type.
- **OpenCL C 3.0** language with feature macros. `any`/`all` on scalars deprecated.

### 1.3 Fundamentals that did *not* change (the model you must hold in your head)
Source: `api/opencl_architecture.asciidoc`.
- **Platform model:** host + one or more *platforms* (vendor implementations, found via the ICD loader),
  each with *devices* made of compute units / processing elements.
- **Execution model:** a *context* groups devices; *command-queues* (in-order or out-of-order) hold
  *commands* (kernel launches, copies, maps); *events* express dependencies and carry profiling data.
- **Index space:** an N-D range of *work-items*, grouped in *work-groups*, optionally in *sub-groups*.
  Barriers sync inside a work-group only; there is no cross-work-group sync inside a kernel.
- **Memory model:** four address spaces (global, constant, local, private); buffers, images, pipes;
  host/device consistency only at synchronisation points (map/unmap, events, flush/finish).
- **Programs:** from source, binary, built-in kernel, or IL (SPIR-V). Build, compile+link, then create kernels.
- Thread safety: every API call is thread-safe except `clSetKernelArg`, `clSetKernelArgSVMPointer`,
  `clSetKernelExecInfo`, `clCloneKernel` (rule dating from 2.1).

---------------------------------------------------------------------------------------------------

## 2. The 3.0.x years: what shipped *inside* 3.0 (v3.0.5 to v3.0.19)

Core 3.0 stayed stable. The movement was in **extensions and clarifications**. The pattern: Khronos
incubates features as `cl_khr_*` extensions, then folds them into core in a minor version (that is exactly 3.1).
Source: `api/appendix_e.asciidoc` revision lists.

| Theme | Extensions added during 3.0.x |
|---|---|
| Sub-group toolkit | `cl_khr_subgroup_extended_types`, `_non_uniform_vote`, `_ballot`, `_non_uniform_arithmetic`, `_shuffle`, `_shuffle_relative`, `_clustered_reduce`, `_rotate`; `cl_khr_work_group_uniform_arithmetic` |
| Math/bit ops | `cl_khr_extended_bit_ops`, `cl_khr_integer_dot_product` (v1 then v2), `cl_khr_kernel_clock` |
| Versioning | `cl_khr_extended_versioning` (declared a core 3.0 feature in v3.0.11 text) |
| Launch tuning | `cl_khr_suggested_local_work_size`; `cl_khr_expect_assume` |
| Async copies | `cl_khr_async_work_group_copy_fence`, `cl_khr_extended_async_copies` |
| Interop/sync | `cl_khr_semaphore`, `cl_khr_external_semaphore` (+ `opaque_fd`, `sync_fd`, `win32`, `dx_fence`), `cl_khr_external_memory` (+ `dma_buf`, `opaque_fd`, `win32`, `android_hardware_buffer`) |
| Graph-style submission | `cl_khr_command_buffer`, `_mutable_dispatch`, `_multi_device` |
| Platform | `cl_khr_pci_bus_info`, `cl_khr_spirv_extended_debug_info`, `cl_khr_spirv_linkonce_odr`, `cl_khr_spirv_queries` |
| Vendor-neutral EXT | `cl_ext_buffer_device_address`, `cl_ext_immutable_memory_objects`, `cl_ext_image_requirements_info`, `cl_ext_image_from_buffer`, `cl_khr_icd` v2.0 |

Notable 3.0.x housekeeping (all clarifications, none removing functionality). Version numbers are the release that contains the change; the old-style appendix wording "Changes from vX" means the release after X, which I first misread:
- v3.0.16: all KHR extension text moved into the main specs; separate Extension spec marked for removal.
- v3.0.17: spec states functionality is **never removed in minor revisions**.
- v3.0.15: SVM explicitly optional for *all* 3.0 devices.
- v3.0.12: definition of "valid object"; kernel-argument count limit; handle comparability rules.
- Many ULP-accuracy table fixes for half-precision (`half_*`, divide, sqrt, tan).

Experimental labelling: from v3.0.19 the word is "experimental" for extensions still subject to change.

---------------------------------------------------------------------------------------------------

## 3. OpenCL 3.1 vs 3.0 (3.1.0, 3.1.1, 3.1.2)

3.1 is a **minor** revision: no feature is removed. Source: `opencl-3.1/.../api/appendix_e.asciidoc`
("Summary of Changes from OpenCL 3.0 to OpenCL 3.1") and `c/appendix_a.asciidoc`.

### 3.1 New or tightened requirements
| Change | Detail |
|---|---|
| **SPIR-V is required** | A 3.1 device must support SPIR-V 1.0 through **1.4** (3.0 made IL optional). Source: appendix_e, glossary |
| **Sub-groups are required** | "Added required support for sub-groups" (`CL_DEVICE_MAX_NUM_SUB_GROUPS`) |
| **OpenCL C 3.1** | A new kernel-language version; spec text for it in `c/` |
| **Extension spec removed** | `OpenCL_Ext` is gone: KHR and EXT extensions are documented in the API/C/Env specs (PR #1516). In the 3.0 tree this is `ext/` and `OpenCL_Ext.txt`; neither exists in 3.1 |

### Promoted extension to core (these were optional extensions in 3.0)
`cl_khr_device_uuid`, `cl_khr_extended_bit_ops`, `cl_khr_integer_dot_product`, `cl_khr_spirv_queries`,
`cl_khr_subgroup_extended_types`, `cl_khr_subgroup_rotate`, `cl_khr_subgroup_shuffle`,
`cl_khr_subgroup_shuffle_relative`, `cl_khr_suggested_local_work_size`.

What that looks like in the headers (`opencl-3.1/OpenCL-Headers/CL/cl.h`, guarded by `CL_VERSION_3_1`):
- New function: `clGetKernelSuggestedLocalWorkSize` (the un-suffixed form of the `...KHR` extension call).
- New device queries: `CL_DEVICE_UUID` 0x106A, `CL_DRIVER_UUID`, `CL_DEVICE_LUID_VALID`, `CL_DEVICE_LUID`,
  `CL_DEVICE_NODE_MASK`; `CL_DEVICE_INTEGER_DOT_PRODUCT_*` (0x1073-0x1075);
  `CL_DEVICE_SPIRV_EXTENDED_INSTRUCTION_SETS`, `CL_DEVICE_SPIRV_EXTENSIONS`, `CL_DEVICE_SPIRV_CAPABILITIES`.
- New types and constants: `cl_device_integer_dot_product_capabilities`,
  `cl_device_integer_dot_product_acceleration_properties`, `CL_UUID_SIZE` 16, `CL_LUID_SIZE` 8.
- `cl_version.h`: adds target value **310**, `CL_VERSION_3_1`; default target moves 300 to 310.
  Bug fixed in 3.1.2: `CL_VERSION_3_1` integer representation (the C spec revision list).
- `CL_API_SUFFIX__VERSION_3_1` added in `cl_platform.h`.

### Behaviour and wording changes
- **`CL_DEVICE_MAX_WORK_ITEM_SIZES` deprecated**, replaced by `CL_DEVICE_MAX_WORK_GROUP_SIZES` (same value 0x1005,
  clearer name). Header comment: `/* deprecated */`.
- **`CL_DEVICE_HOST_UNIFIED_MEMORY` un-deprecated** and clarified (deprecated since 2.0 per appendix E; the 3.0 header still carries `/* deprecated */`; see TRAPS.md #12).
- **`clSetKernelArg`** may now set a local-memory argument to size **zero**; its text was refactored.
- **Memory model, inclusive scope relaxed:** before 3.1 two atomic actions needed the *same* scope to be
  "inclusive"; now each work-item/thread only needs to be inside the other's scope. This affects
  mixed-scope atomic code. (glossary diff)
- **Event completion as sync point:** 3.1.0 made observing `CL_COMPLETE` a synchronisation point; **3.1.1
  reverted it** over performance regressions (internal issue 386, PR #1558). Net result in 3.1.2: same as 3.0.
- **Custom devices and built-in kernels redefined:** 3.0 said custom devices support only built-in kernels and
  cannot use a kernel language; 3.1 says a custom device is a specialised device supporting a subset of the runtime,
  not conformant, may return implementation-defined errors. A built-in kernel is "provided by an implementation",
  may run on specialised hardware.
- Clarifications: `clGetSupportedImageFormats` for devices without images, `CL_PROGRAM_SOURCE` null-string,
  non-uniform work-group support conditions, `clSetProgramSpecializationConstant` with separate compile/link,
  `CL_MEM_KERNEL_READ_AND_WRITE` flag, atomics, sub-group function text.
- Many new/consistent error conditions: `clCompileProgram`, `clLinkProgram`, `clSetKernelExecInfo`,
  `clEnqueueNDRangeKernel` with a zero local size, memory object APIs.

### OpenCL C 3.1 vs 3.0 (kernel language)
- `printf` gains the **`z` and `t`** length specifiers (size_t / ptrdiff_t).
- Core now contains: extended bit ops, integer dot product, sub-group extended types / rotate / shuffle / shuffle-relative.
- Fixed `fmin` for `half`; clarified NaN-to-integer saturated conversions and `any`/`all`.
- Removed the "Extending Attribute Qualifiers" section and some SPIR-V references.
- 3.1.1: version requirements in the C spec are about the OpenCL C *language* version, not device/platform version.

### Extension-level changes between the trees
Added in 3.1 sources: `cl_khr_unified_svm` (experimental, still under development), `cl_khr_icd_unloadable`
(`CL_PLATFORM_UNLOADABLE_KHR`, lets an ICD say the loader may unload it), `cl_img_safety_mechanisms`,
`cl_img_unified_svm_external_memory_dma_buf`, `cl_intel_kernel_allocations_info`,
`cl_intel_subgroup_matrix_multiply_accumulate_tf32`.
Finalised (no longer experimental) in 3.1.2: `cl_khr_command_buffer`.
Still experimental: `cl_khr_command_buffer_mutable_dispatch`, `cl_khr_external_memory_android_hardware_buffer`,
`cl_khr_unified_svm`.

### What 3.1 does NOT change
SVM stays optional. Device-side enqueue, pipes, generic address space, fp64, images: all still optional.
The optional-feature model (appendix H) carries over. Only sub-groups and SPIR-V moved from optional to required.

---------------------------------------------------------------------------------------------------

## 4. "Onward": what comes after 3.1

- **Nothing newer is published.** On 2026-10-03 the `main` branch of KhronosGroup/OpenCL-Docs is the same
  commit as tag `v3.1.2` (219be24). There is no 3.2 or 4.0 spec text to diff.
- **Where the next features are visible** is in extension branches on that repo. Branch names seen
  (contents not read here; see the proposal tester in the tools for a way to check one): several extension and sync-related branches exist on that repo.
- **Reading the pattern (background / inference):** the 3.0 to 3.1 path suggests what a future minor release
  would promote: extensions that have finalised, shipped in several implementations and have conformance tests.
  Candidates by status in the 3.1.2 sources are `cl_khr_command_buffer` (finalised in 3.1.2),
  the semaphore and external memory families (finalised in v3.0.15), and `cl_khr_kernel_clock` (finalised v3.0.18).
  Unified SVM is the largest in-flight item and is labelled experimental. This is a guess about direction,
  not a published plan.
- **Headers:** `v2026.05.29` already targets 310 by default. Header releases lead spec text by design.

---------------------------------------------------------------------------------------------------

## 5. Anchor to reality: this machine

Source: `clinfo` output, rusticl (Mesa 25.2.8), AMD Radeon renoir.

| Item | Reported |
|---|---|
| Platform / device version | OpenCL 3.0; platform FULL_PROFILE, **device EMBEDDED_PROFILE** |
| OpenCL C | 3.0, 1.2, 1.1, 1.0 all accepted |
| OpenCL C features | int64, images, read-write images, 3D image writes, subgroups, integer dot product (4x8 packed and unpacked), kernel_clock (device, sub-group), `unorm_int_2_101010` |
| SVM | coarse-grain buffer SVM only (`CL_DEVICE_SVM_CAPABILITIES` = `CL_DEVICE_SVM_COARSE_GRAIN_BUFFER`; no fine-grain, no atomics). The default `clinfo` text printed "(core)" and "SVM 0 bytes", which I first misread as "none"; the `--raw` output is the evidence |
| Pipes, generic address space, device enqueue | not supported |
| Atomics | relaxed order, work-group scope only (the minimal 3.0 level) |
| Non-uniform work-groups | no |
| fp64 | not supported; fp16 is (`cl_khr_fp16`) |
| IL | SPIR-V 1.0 to 1.6 |
| Sub-groups | up to 16 per work-group |
| Latest conformance passed | `v0000-01-01-00` (i.e. none recorded) |

How this maps onto the versions:
- It is a good example of the 3.0 design: an *embedded-profile* GPU with a minimal atomics model and only
  coarse-grain SVM (no generic address space, pipes, device enqueue or fine-grain SVM) still counts as a 3.0 device.
- It already meets the two 3.1 "newly required" items on paper: sub-groups (yes) and SPIR-V 1.0 to 1.4 (it reports through 1.6).
  It does not claim 3.1, and nothing here says rusticl is tested against 3.1.
- Several 3.1 promoted features appear here as ordinary 3.0 features (integer dot product, kernel clock),
  because rusticl exposes the extension functionality.
- Because the system headers are 3.0, the 3.1 symbols (`clGetKernelSuggestedLocalWorkSize`, `CL_DEVICE_UUID`, ...)
  are not declared locally. To experiment, compile against `opencl-3.1/OpenCL-Headers` and guard on
  `CL_VERSION_3_1`; at runtime the platform must report 3.1 for core 3.1 calls to be valid.

---------------------------------------------------------------------------------------------------

## 6. A reading path

1. `opencl-3.0/spec-pdf/OpenCL_API.pdf` chapters 3 (execution/memory model), 4 (platform layer), 5 (runtime).
2. Appendix H of the API spec (`api/appendix_h.asciidoc`): the optional-feature contract. Read it before writing portable code.
3. `OpenCL_C.pdf` for the kernel language, with the feature macros.
4. `OpenCL_Env.pdf` for the SPIR-V environment (needed for 3.1 since IL is required).
5. Then diff: `diff -ru opencl-3.0/OpenCL-Headers opencl-3.1/OpenCL-Headers` and
   `diff -u opencl-3.0/OpenCL-Docs-src/api/appendix_e.asciidoc opencl-3.1/OpenCL-Docs-src/api/appendix_e.asciidoc`.

## 7. Caveats on this guide
- The 3.0 PDFs came from the Khronos registry (latest 3.0 build); the 3.0 sources are tag v3.0.19. I did not verify
  the PDF build matches v3.0.19 exactly.
- The 3.1 side was read from source files, not a rendered PDF. I read the appendices, glossary, architecture and
  header diffs; I did not read the full 3.1 API chapters line by line (106 API files differ, many only in wording).
- Branch names in section 4 are from `git ls-remote` only.
