# Independent review of the v2 hierarchy and optical bridge

Review date: 2026-10-11. Reviewer role was separate from the geometry and optical module implementers. This is a correctness review of the represented model and its data transfers. It is not validation against measured cotton, silk, cupra, linen, blends, or product photographs.

## Assessment

The implemented v2 is a usable **controlled forward-simulation reference**: it gives explicit fiber/ply/yarn ownership, rectangular draft semantics, parent-arclength twist conventions, bounded procedural variation, a numerical geometry audit, and an optical scene that retains constituent materials and reports unsupported reductions.

The inspected implementation correctly distinguishes a finite procedural fabric patch from a textile mechanics solution, and a local 2D cylinder calculation from wave propagation through a complete woven fabric. It does not claim to reproduce the learned FabricGen pipeline, Tang's ASGGX inverse capture, Weavecraft's multilayer mechanics or Yu's complete hybrid renderer. These distinctions are material to evaluating the research contribution; see [literature audit](literature_engine_v2.md).

One false-certification bug was found and fixed during this review. A second change made fiber records truly immutable rather than merely read-only by convention. After those fixes, the combined new-module test scope below passed **59 tests**, including actual calls to the wave, ray and Mitsuba solvers. No further blocking defect was found in the inspected scope. This statement is limited to these implementations, tests, fixtures and declared approximations.

## 1. Findings and corrective actions

### R1 — Negative batch size could incorrectly certify intersecting fibers

**Observed failure:** with two orthogonal centerline segments crossing at their interiors and both radii 0.002 mm, the standard audit correctly returned a minimum clearance of −0.004 mm. Passing `batch_size=-1` skipped the narrow-phase loop and returned `certified_separated=True`, zero tested pairs and the positive probe margin as the clearance lower bound.

This was a genuine correctness defect because a runtime control could bypass all distance checks while returning a geometric certificate.

**Correction:** `audit_clearance` now validates `batch_size` and `max_candidate_pairs` as positive integers before the broad phase, rejecting negative, zero, Boolean and nonintegral values. The original intersecting fixture and invalid-input regressions are in [test_engine_v2_review.py](../tests/test_engine_v2_review.py).

### R2 — Frozen geometry records still allowed their arrays to become writable

**Observed issue:** the original `FiberCurve` dataclass was frozen and its owning arrays had the writable flag disabled. `record.points_mm.setflags(write=True)` nevertheless succeeded. This could alter geometry after a caller had treated the record as immutable.

**Correction:** the implementation now creates arrays backed by immutable bytes. Direct modification and reenabling the writable flag are rejected. The independent regression checks both points and radii. The optical-scene records already used this stronger storage rule.

### Source/export integrity improvements inspected

The optical implementer additionally hashes the scene content, export manifest and each curve file; enforces slice shapes and right-handed orthonormal frames; records B-spline conversion error; and records coordinate/radius quantization to the pinned renderer's float32 storage. These were inspected and their existing tests were run as part of the 59-test scope. Hashes detect mismatched content within this workflow; they do not constitute an external attestation that a physical sample was measured correctly.

## 2. Mathematical contracts reviewed

### 2.1 Topology and interpolation

Rows denote weft picks, columns denote warp ends, and one means warp above weft. Rectangular periodic indexing and negative padding indices use the appropriate axis length. Family exchange complements the transposed matrix. Cyclic float diagnostics handle repeats spanning the boundary and report entirely unbound yarns separately.

The quintic crossing interpolation has zero first and second derivatives at its endpoints and cannot overshoot two adjacent crossing heights. Its prescribed heights are not solved contact positions. Lateral waviness is anchored at crossings. These are kinematic choices and are consistently labeled as such in the source metadata.

### 2.2 Frames, twist and procedural irregularity

The local frame uses \(n_2=\hat t\times n_1\); positive twist therefore has an explicit right-handed meaning. Twist at each level uses that parent's measured arclength. The tests compare frame transport to an analytic Bishop frame of a helix, assess convergence of helical chord length, reject degenerate/cusped input and test rigid transformations with an explicitly transformed initial frame.

The independent review adds a coupled mirror test. Reflecting \(y\mapsto-y\) while reversing both yarn and ply handedness, both phase signs and local transverse offsets gives the reflected full nested fiber geometry. This checks the two-level convention, not merely a single helix. Another independent test reverses fiber enumeration and verifies that identity-keyed migration remains exactly unchanged for each fiber ID.

Radial migration and the optional compact loop are geometric perturbations with explicit bounds. The loop alters the existing fiber's path length at fixed radius, so it changes the cylinder-volume proxy; no mass-conservation claim is made. A complete microgeometry repeat is not forced to close its frame/twist/migration phases. `geometry_tileable=False` is appropriate even when the draft and yarn centerline repeat.

### 2.3 Continuous clearance of the represented polylines

Each represented straight segment is enclosed by a closed capsule. If its midpoint is \(m_i\), segment half-length \(h_i\) and radius \(a_i\), any pair whose surface distance is at most the probe margin \(p\) must obey

\[
\|m_i-m_j\|\le h_i+h_j+a_i+a_j+p.
\]

The implemented global search radius \(2\max_i(h_i+a_i)+p\) is therefore conservative for the broad phase. Retained pairs receive segment-to-segment distance checks. The returned minimum lower bound is limited by the probe margin because untested far pairs are only proved farther than that margin.

The certificate applies to **different fibers represented as constant-radius polyline capsule unions**. It does not assess same-fiber self-contact, contact force, a relaxed mechanical state, arbitrary curved surfaces, or an unexamined export. The separate test with tightly twisted helices correctly shows that equal-section packing alone cannot certify global separation.

### 2.4 Spline and float32 transfer

For the endpoint-preserving cubic conversion, on a source segment the spline-to-chord displacement is a nonnegative weighted sum of two second control differences. Its weight sum is at most \(1/6\). This yields the implemented bound

\[
e_{\rm smooth}\le\tfrac16\max_i\|\Delta^2P_i\|.
\]

A cubic B-spline is a convex combination of its local controls, so the maximum float32 control displacement bounds the resulting spline centerline displacement. Radius quantization adds a separate tube-thickness error. If every source pair has gap at least \(g\) and every exported tube moves by at most \(e\), then

\[
g_{\rm export}\ge g-2e,
\qquad e=e_{\rm smooth}+e_{\rm control32}+e_{\rm radius32}.
\]

The implementation combines these terms correctly. This is a geometric bound for the ideal spline/tube defined by the stored float32 controls. It does not bound every floating-point operation in acceleration traversal or shading. A smoothing bound alone is not a contact certificate; its combination with a source clearance certificate can establish positive geometric separation.

### 2.5 Optical units and local reductions

The passive \(n+i\kappa\), \(e^{-i\omega t}\) convention is consistent with the intensity absorption coefficient \(\mu_a=4\pi\kappa/\lambda\). Vacuum wavelength, host-medium wavelength and relative refractive index are distinguished when producing 2D wave inputs. The ray and hair adapters use real-index Fresnel coefficients with Beer absorption and state their weak-absorption approximation.

The local slice checks circularity, one supported centerline intersection per selected fiber, local tilt/curvature, axial support and circle separation. A failed selected fiber is retained in the diagnostic failure rather than dropped. The tilt-derived ellipse semiaxis \(a/|\cos\beta|\) is reported; oblique/curved bundles do not silently enter the exact circular-cylinder path. Strict eligibility remains a **local** geometric condition, not proof that an infinite-cylinder calculation predicts the full finite fabric.

Per-fiber material/radius assignments survive hierarchy adaptation and export grouping. A material blend is not collapsed into an average refractive index. The tangent tensors and lateral-area sums are descriptive statistics; the source does not mislabel them as opacity, SGGX fits or BSDFs.

## 3. Executed tests

The combined command on the reviewed source snapshot was:

```python
import unittest
patterns = (
    "test_weave_draft.py", "test_hierarchy.py",
    "test_optical_scene.py", "test_engine_v2_review.py",
)
suite = unittest.TestSuite(
    unittest.defaultTestLoader.discover("tests", pattern=p) for p in patterns
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful()
```

Result: **59 tests passed in 7.502 s** on the execution environment used for this review. Runtime is an observation, not a performance guarantee. These are the four new-module suites; the parent integration report separately records the full legacy-plus-v2 regression suite.

| Suite | Count in reviewed run | Important independent expectation |
| --- | ---: | --- |
| `test_weave_draft.py` | 8 | Rectangular axes, periodic crossing lookup, correct family exchange, `C2` derivative behavior, lift-plan round trip |
| `test_hierarchy.py` | 17 | Analytic helix length/frame convergence, parent-arclength nested twist, known skew/intersecting segments, geometry refinement and provenance |
| `test_optical_scene.py` | 27 | Beer field/intensity relation, analytic cubic bound, float32 transfer, strict slice failures, host-medium units, actual Mitsuba and 2D wave/ray execution |
| `test_engine_v2_review.py` | 7 | Reviewed-bug regressions, two-level mirror symmetry, order-independent migration, segmentation invariance and actual-solver similarity/permutation |

### Independent end-to-end optical similarity check

The fixture contains two straight circular fibers with different radii and synthetic complex spectra in a host with index 1.23. Both geometry and vacuum wavelengths were multiplied by 1.7, while retaining the same complex indices at corresponding wavelengths. The physical expectation is invariant dimensionless Maxwell behavior, 2D cross-sections proportional to length, and invariant Beer-attenuated ray fractions.

| Quantity | Observed scaled/original ratio or discrepancy |
| --- | --- |
| `Ez` scattering cross-section | 1.699999999999997 |
| `Ez` extinction cross-section | 1.6999999999999995 |
| `Ez` absorption cross-section | 1.700000000000231 |
| `Hz` scattering cross-section | 1.6999999999999968 |
| `Hz` extinction cross-section | 1.6999999999999993 |
| `Hz` absorption cross-section | 1.7000000000002191 |
| Maximum differential-scattering discrepancy after dividing by 1.7 | approximately \(8.53\times10^{-14}\) in solver units |
| Ray power fractions | unchanged to the asserted 11 decimal places with the same 1,500-ray seed |

The call chain exercised `OpticalScene → extract_bundle_section → wave_inputs/ray_inputs → cluster_scattering/trace_bundle`; the test did not feed manually converted geometry directly to the solvers. It consequently checks a coupled unit/material-transfer property. It is not a high-ray-count accuracy benchmark or proof that geometric optics matches the wave result.

## 4. Independent check of the saved fabric/export result

The stored `data/optical_bridge_v2/fabric_geometry` and `fabric_scene.json` were reloaded. Every fiber's ID, parent, material, points and radius were compared exactly across the hierarchy/scene boundary. The clearance audit was rerun, and the conversion/quantization error was recomputed from each source fiber and checked against the export manifest.

| Item | Independently confirmed value |
| --- | ---: |
| Fibers | 98 |
| Different-fiber segment pairs examined | 212,657 |
| Source polyline clearance lower bound | 0.002 mm = 2 μm |
| Maximum smoothing + control/radius float32 displacement bound | 0.000041154899845416455 mm |
| Exported ideal spline-tube separation lower bound | 0.0019176902003091671 mm ≈ 1.91769 μm |

Optical scene content hash:

```text
e3bea2dc5068e39abdddaed5de122b0930a2080bbfc8c58d8f986fecd18a6658
```

The four saved 450/650 nm reflection/transmission images are finite-sample, single-wavelength scalar proxies. Their image means are camera radiance statistics, not hemispherical reflectance/transmittance. The optical report correctly avoids adding those means as `R+T` or treating small differences between separately seeded 64-spp renders as statistically established spectral effects.

## 5. Remaining limits and next meaningful gates

- **No mechanical solution:** prescribed crossings, bounded offsets and positive clearance do not predict yarn flattening, tension, compression, friction, drape or loom stability. Multi-layer woven blocks remain beyond the binary single-layer draft model.
- **No physical material calibration:** optical constants are explicitly synthetic in the example. Material labels and geometrical resemblance do not establish optical agreement with silk, cotton, cupra or a specified blend.
- **Restricted cross-sections:** the explicit engine and supported adapters use constant circular fiber radii. Noncircular fibers and birefringence need additional constitutive/geometry models.
- **No complete wave cloth solver:** only eligible local parallel bundles enter the exact 2D cylinder solver. A 3D weave normally fails the strict reduction because its fibers curve and tilt. This is a correct rejection, not a missing flag to suppress.
- **No solved aggregate appearance:** orientation moments and unoccluded areas are useful inputs but do not determine a unique SGGX/BSDF/BTF. Aggregate kernels must be calibrated and compared against a specified reference.
- **No inferred inverse uniqueness:** matching a photo can yield plausible fiber statistics without recovering every actual fiber. Measurement design requires held-out illumination/view comparisons and physical samples.
- **Finite and declared discretization:** refinement tests reduce geometric error for the controlled fixture; they do not supply a universal error bound for arbitrary user-defined parameters or caller-supplied stand-alone yarn sampling.

The next useful validation is a matched family of explicit microgeometry and material cases, with converged reference optics, that measures where local/aggregate models succeed or fail. Only after that comparison should added angular, spectral or polarization measurements—and a corresponding metaelement—be evaluated against a strong RGB acquisition baseline.

## Reviewed source snapshot hashes

These hashes identify the files inspected when the 59-test run and saved-artifact check were performed. Later edits require the corresponding relevant checks to be rerun.

| File | SHA-256 |
| --- | --- |
| `textile_sim/weave_draft.py` | `13704a2ade4f6ea7c9f43de0c23e077861c2094fbcd937ec13ca3b2d52efc540` |
| `textile_sim/hierarchy.py` | `0ccea74ef08c735cbcf9c22682bd7a51a59423efb9599e743d23f1cb08ca3a73` |
| `textile_sim/optical_scene.py` | `8575c32cba21d784c1b6d19d3fa66723e0331d4a1be99756322efd488044e061` |
| `tests/test_engine_v2_review.py` | `692e04eaf2bf16f31e124567859676998c10f6f9301d0ff52b6c546a9a70c0f5` |
