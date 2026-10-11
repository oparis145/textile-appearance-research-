# v0.4 material-coordinate transport: independent review

Review date: 2026-10-11. This review concerns the kinematic bridge between the
existing yarn-height mechanics and explicit fiber geometry. It is not a
validation of measured textile mechanics or of a complete ray–wave cloth BSDF.

## 1. Why this change is required by the research question

The project asks whether geometry and additional angular/spectral measurements
can explain and reduce the difference between photographed and observed fabric
appearance. A controlled comparison needs to distinguish a change of state of a
specified specimen from generating a different specimen from the same recipe.
The v0.3 bridge re-evaluated twists and excursions at *current* parent arclength.
Its fiber IDs denoted construction components; they did not establish material
point correspondence. Holding node count fixed does not solve this problem.

The v0.4 objective is narrower and testable: attach fixed reference labels to
fiber vertices, specify the correspondence between old and new parent curves,
and transport the stored offsets. This removes one regeneration confound. It
does not by itself prove physical deformation, measured appearance fidelity,
or an advantage over RGB or conventional optics. This is an enabling
implementation change, not a claim of a new RMF or rod theory.

## 2. Mathematical contract and independent derivations

Let a reference fiber be sampled at material labels `S_i` and let `xi_i` denote
the *separate* parent-coordinate correspondence. Labels derived from a fiber's
reference arclength are fixed after binding. They must never be replaced by
the current fiber arclength, normalized current arclength, or an array index
silently assigned to a different mesh.

For a reference parent curve `p_0(xi)` with orthonormal frame `B_0(xi)`, the
stored three-component offset is

\[
q_i=B_0(\xi_i)^T[X_i-p_0(\xi_i)].
\]

A prescribed current curve and frame then define the kinematic map

\[
x_i=p_1(\xi_i)+B_1(\xi_i)q_i.
\]

The same operation is applied recursively to the yarn-to-ply and ply-to-fiber
levels. Keeping all three offset components avoids deleting longitudinal
offsets merely because a sampled RMF normal is not exactly perpendicular to a
child's displacement. Recursion defines a kinematic rule; it does not derive
the full three-dimensional deformation gradient of a solid fiber bundle.

### Objectivity

For a proper rigid rotation `Q` and translation `b`, transform every input
position as `Q x + b` and every prescribed director as `Q n`. An objective
transport must produce `Q x_i + b`, while lengths, stretches, volumes, material
labels and IDs remain unchanged. Choosing the initial normal afresh from a
global coordinate axis generally fails this physical comparison.

### Axial stretch and material phase

For a straight parent `p_0(S)=(0,0,S)` and a reference helical fiber

\[
X(S)=(a\cos kS,a\sin kS,S),
\]

the prescribed parent stretch `p_1(S)=(0,0,\Lambda S)` with unchanged
cross-section produces

\[
x(S)=(a\cos kS,a\sin kS,\Lambda S).
\]

Thus the phase at each material label remains `k S`; turns per unit current
parent length become `k/(2 pi Lambda)`. For a finite segment of reference
axial increment `dS`, its exact polyline stretch is

\[
\lambda_e=
\frac{\sqrt{4a^2\sin^2(k\Delta S/2)+\Lambda^2\Delta S^2}}
     {\sqrt{4a^2\sin^2(k\Delta S/2)+\Delta S^2}}.
\]

This provides an oracle independent of the transport implementation. A
regenerator using `cos(k Lambda S)` represents different phase labels.

### Segment volume accounting

The one-dimensional circular-cylinder bookkeeping measure is

\[
V_e=\pi r_e^2\ell_e\quad[\mathrm{mm}^3],\qquad
\lambda_e=\ell_e/\ell_{0,e}.
\]

With fixed radius, volume changes with length. With the optional rule
`r_e=r_0/sqrt(lambda_e)`, each segment's cylinder proxy equals its reference
value. This algebra does **not** establish a globally injective, incompressible
three-dimensional deformation: bends, tube joints, section shape, overlap,
contact and constitutive response are additional questions. Mass follows from
this proxy only after an explicit density assumption. Uniform geometric unit
scaling by `a` must scale lengths/radii by `a`, volumes by `a^3`, and leave
stretches unchanged.

### Frames, prescribed orientation and twist

An RMF is a useful geometric reference, not a solved material orientation. In
rod theory a separate rotation angle relates the material frame to a Bishop
frame, and its variation contributes twist strain. The reference yarn director
and a prescribed target director therefore form part of the transport input.
Neither centerline shape nor an RMF alone determines arbitrary applied torque
or a general twist field. [Bergou et al. 2008, §§4.1–4.2 and 5](https://www.cs.columbia.edu/cg/pdfs/143-rods.pdf).

Independent projection of a yarn normal into two different ply-normal planes
can introduce a nested orientation change when ply tangents differ. The
implementation author was asked to carry the reference ply seed with the
parent rotation and then apply the declared minimal tangent alignment, rather
than assume two projections define an invariant frame correspondence.
Antiparallel tangent alignment requires a declared additional axis or rejection.

An analytical counterexample makes the projection problem concrete. Take the
yarn tangent along `z`, ply tangent `(sin(theta),0,cos(theta))`, and spin the
yarn's reference normal from `x` by `alpha`. The projected normal's angle in
the ply plane is `atan2(sin(alpha), cos(theta) cos(alpha))`. At `alpha=45 deg`,
changing `theta` from `45 deg` to `60 deg` changes this angle from
`54.7356103 deg` to `63.4349488 deg`: independent projection introduces an
extra `8.6993385 deg` difference. Carrying a reference seed by a declared proper
rotation is therefore a substantive requirement, not a cosmetic convention.

### Support, reversibility and contact

Interpolation requires explicit monotonically increasing material coordinates
whose domain covers all required labels. More target vertices do not imply
correct correspondence. Unsupported labels must not be clamped to the last
target vertex or extrapolated without an explicit model.

Replaying from an immutable reference prevents cumulative resetting of phase
and labels. It is not a claim that arbitrary coarse resampling, frame transport
through a deformation history, or contact evolution has an exact inverse.
Current clearance must be checked on transported geometry: a reference
envelope or a centerline constraint is not automatically a certificate for a
new fiber bundle.

## 3. Primary-source basis and provenance

| Source | Material actually inspected | Use and limit |
|---|---|---|
| Wang, Jüttler, Zheng, Liu, *Computation of Rotation Minimizing Frames*, TOG 27(1), 2008, DOI [10.1145/1330511.1330513](https://doi.org/10.1145/1330511.1330513) | [Microsoft Research publication](https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/) and [author-hosted PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/12/Computation-of-rotation-minimizing-frames.pdf) | Geometric minimal-rotation frame and double-reflection reference. The paper's convergence result does not automatically apply to this pipeline's polyline interpolation and estimated tangents. |
| Bergou, Wardetzky, Robinson, Audoly, Grinspun, *Discrete Elastic Rods*, TOG 27(3), 2008, DOI [10.1145/1360612.1360662](https://doi.org/10.1145/1360612.1360662) | [Author PDF](https://www.cs.columbia.edu/cg/pdfs/143-rods.pdf), framed-curve representation, Bishop/material frames, time transport, twist energy and inextensibility constraints | Establishes the distinction between geometry, material-frame variables, elastic evolution and constraints. v0.4 does not implement the full DER dynamics or quasistatic torque equilibrium. |

No author implementation was copied into the reviewer tests. Formula-based
oracles below are independent geometric and dimensional derivations.

## 4. Independent verification record

The reviewer authored [18 tests](../tests/test_material_transport_review.py)
separately from the implementation's own tests. The final targeted invocation
was:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m unittest tests.test_material_transport_review -v
```

Result: **18 tests passed, 0 failures, 0 errors, 0 skips**, in `0.835 s` for this
invocation. This is a targeted review run, not the repository-wide final test
count. At the reviewed snapshot:

- `textile_sim/material_transport.py` SHA-256:
  `f71e2e8cb232945d1d16919e803a1832bfdbf5cfa51012e540e038147653eb10`.
- `tests/test_material_transport_review.py` SHA-256:
  `337abee0d2ac7e4590dc9ddfcd4e399a603080f1e70aadb592cebf89ae76eb33`.

| Independent oracle or counterexample | Verified condition |
|---|---|
| Straight parent with a helical fiber under uniform axial stretch | Exact vertex positions and finite-chord stretch; frozen reference phase differs from regeneration |
| Nonuniform parent stretch | Segment cylinder-volume proxy conservation in the optional mode; fixed-radius volume changes; incompatible optical export rejected |
| Joint rigid motion of a nonrigid, two-ply case | Objectivity of the resulting points, strains and volumes with co-rotated directors |
| Simultaneous reference/target frame-gauge change | Nested fiber positions agree after the revised child-director rule |
| Unchanged centerline, changed target starting director | Marked fibers rotate, demonstrating that centerline position alone does not supply the orientation |
| Framed-point forward/inverse map with distinct meshes and axial offsets | Labelled-point algebraic roundtrip retains all three offset components |
| Different target knot mesh | Explicit material coordinates recover the exact straight-axis deformation |
| Analytic planar circle with a binormal-offset fiber | Chord-sagitta error `1-cos(0.5/(N-1))` is recovered for 11/21/41 knots; position interpolation has second-order convergence in this fixture |
| Current arclength substituted for material labels | Changed reference endpoint rejected |
| Insufficient parent domain | No silent extrapolation or endpoint clamping |
| Uniform length-unit scaling | Points, labels and radii scale linearly, segment volumes cubically, strain stays unchanged |
| Reordered dictionaries and fiber storage | Parent identity and output positions remain associated by ID |
| Altered parent correspondence under the shared-index declaration | Rejected; all semantic correspondence maps are also included in the reference hash |
| Forged state with a different radius mode | Rejected before a false segment-conservation claim is possible |
| Forged state with a different material reference | Rejected |
| Translated fiber pose preserving every scalar length/volume | Rejected because it does not replay the declared parent map |
| One ply attributed to two yarns | Rejected at binding |
| Optical export of a transported state | Reference-only clearance audit is discarded and a new audit is required |

### Findings and corrections retained in the record

1. **Nested frame orientation:** the analytical counterexample in §2 showed why
   separate normal projections are insufficient. The author implemented parent
   rotation followed by minimal tangent alignment. The subsequent objectivity
   and simultaneous-gauge tests pass.
2. **Reference digest omitted a used correspondence:** the first 16-test run
   demonstrated that changing `ply_parent_material_coordinates_mm` could leave
   the reference digest unchanged. A synthetic reference kept the digest
   `774cf6d814305a7573c8daddee7804daa97ae92205ca1ea82a7252cf7b94049c`
   under that edit. The author now validates the declared correspondence and
   hashes the parent map and coordinate arrays.
3. **Public state construction could overstate its identity:** the same first
   run demonstrated that a constant-radius state could be relabelled as the
   conserving mode, or associated with a different material reference. The
   author added explicit reference/order/mode checks and replay of parent and
   child positions/directors. The additional translated-fiber test confirms
   that scalar strain/volume checks alone are not used as proof of the map.

The initial targeted run had **13 passes and 3 failures** in `0.465 s`; all three
failures corresponded to findings 2–3. Two further independent tests were added
afterward. No review test was removed and no failing review tolerance was
loosened to obtain the final pass.

## 5. Interpretation for controlled optical experiments

The results support a fixed-label, prescribed hierarchical transport **within
the declared correspondence and frame model**. In a production comparison,
report the minimum, maximum and length-weighted distribution of segment strain,
as well as aggregate length/volume. Large compression and extension can cancel
in the aggregate: a small net volume-proxy change cannot establish local
inextensibility or acceptable constituent stress.

Current fiber clearance and renderer geometry checks remain separate gates.
Variable segment radii remain excluded from the constant-radius optical
adapter. A new radius-aware adapter must preserve material-volume accounting
and validate joint geometry, absorption and projected area before the optional
radius mode can be used in the same optical comparison. None of these tests
establishes measured material fidelity, constitutive equilibrium, a full fabric
wave solution, perceptual benefit, or a metasurface measurement advantage.

## 6. Independent saved-artifact verification

The independent verifier
[`verify_material_transport_artifacts_v4.py`](../verify_material_transport_artifacts_v4.py)
reads the saved arrays and recomputes the evidence. It does not import the
experiment driver and does not execute a renderer. The final canonical
experiment was checked with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python verify_material_transport_artifacts_v4.py \
    --input data/material_transport_v4 \
    --output scratch_runs/v4_independent_final
```

The result was **passed**. The producer ledger's **32 output files** matched
their bytes, and all **108 saved monochromatic renders** were consistent with
the nine state/light arrays of shape `4 × 64 × 64 × 3`: four seeds, three
states, three lights and three wavelengths. The six paired comparisons were
recomputed by averaging each image in float64 and forming intervals across
the four paired seeds. This does not add another 108 renders to the experiment
count.

| Evidence layer | Independent calculation |
|---|---|
| File and semantic identity | Producer completion and exact output-file ledger; raw NPZ hashes; reference/state digests from saved arrays, IDs and parent correspondence |
| Material transport | Parent domains, fixed fiber labels, proper orthonormal frames, nested parent/director transport and labeled fiber positions |
| Strain and volume | Raw positions to segment lengths and stretch; both radius modes; segment cylinder-volume proxies and aggregate/family totals |
| Three geometry states | Saved hierarchy summaries, fiber and parent IDs, reference/current pose identity, regenerated/transported differences and fresh different-fiber clearance |
| Optical geometry adapter | Scene curves and materials, exported spline controls/radii, curve-file hashes, microstructure statistics and export displacement/clearance bounds |
| Reduced projected-area models | Saved matrices applied to raw held-out directions, exact segment projected areas, grouping and reported error metrics |
| Rendered results | Finite nonnegative radiance, seed/wavelength/shape/count consistency, means, standard errors and paired confidence intervals |

The saved arrays reproduce the following local and aggregate diagnostics:

| Quantity | Recomputed value |
|---|---:|
| Fibers / vertices / segments | 42 / 8,106 / 8,064 |
| Reference fiber length | 40.61116531446068 mm |
| Transported fiber length | 40.62912535957995 mm |
| Relative total length change | +0.0442244023% |
| Minimum / maximum segment stretch | 0.8596802448 / 1.1412012899 |
| Reference-length-weighted RMS engineering strain | 1.7282056828% |
| Constant-radius relative cylinder-volume change | +0.0442244023% |
| Conserving-mode maximum absolute relative segment-volume residual | 6.66 × 10⁻¹⁶ |
| Regenerated/transported RMS vertex distance | 7.73440082 × 10⁻⁵ mm |
| Regenerated/transported maximum vertex distance | 2.08707538 × 10⁻⁴ mm |

The approximately −14.0% to +14.1% local segment strain is a consequence of
this prescribed sampled kinematics. The much smaller aggregate change must
not be used to describe the fibers as locally inextensible or the state as
an elastic equilibrium. The conserving radius option satisfies its discrete
cylinder-volume formula; it does not resolve those mechanical limitations.

### Verification of the verifier

The separate artifact tests ran with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m unittest tests.test_material_transport_artifacts_v4 -v
```

Result: **7 tests passed, 0 failures, 0 errors, 0 skips**, in `0.383 s`.
Two positive tests exercise rendered-array and explicitly skipped modes.
Their radiance arrays are an analytical fixture; no renderer was executed
to create that fixture. Five negative tests modify the artifacts as follows:

1. Change a reported segment stretch while retaining its source positions.
2. Flip a frame normal to obtain an orthonormal matrix with determinant −1.
3. Insert nonfinite radiance.
4. Invent a paired mean difference inconsistent with the image arrays.
5. Remove an original material-coordinate array.

Each negative case refreshes the affected local checksum and the producer
output ledger before verification. All are rejected on numerical or structural
inconsistency, rather than passing only because an old hash detects the edit.
The verifier also rejects missing, incomplete or failed producer artifacts
and prevents writing its output inside or above the input directory.

At this reviewed snapshot:

- `verify_material_transport_artifacts_v4.py` SHA-256:
  `69577e1098a243b1c3c7b5b3567c3e3e0a4e3611444b18fced3b891b783f4ba3`.
- `tests/test_material_transport_artifacts_v4.py` SHA-256:
  `dd1f5b638df5d8cc401515325044b6bbf9e9ec76d38c7dc47a25d292b155d72f`.

### Boundaries of this artifact check

The independent review result is preserved byte-for-byte in
[the versioned review artifact](../data/validation_v4/independent_review/verification_summary.json),
with [copy provenance](../data/validation_v4/independent_review/provenance.json).
The root's separate final runner audit is in
[the final audit manifest](../data/validation_v4/final_artifact_audit/run_manifest.json).
These records distinguish rechecking saved radiance from generating new samples.

The standalone verifier checks the saved producer completion status and
output ledger. It does not reopen historical external input paths or check
the current source tree against the producer's source record. The execution
runner separately checks current source hashes and the inputs declared for
its selected stages. A verify-only stage treats the saved experiment as its
input; it does not establish that an original external input directory still
exists or still has its historical contents.

Saved counts are consistency checks on arrays and records, not an independent
proof of invocation history. The renderer curve audit concerns different
fibers; self-contact and contact mechanics remain outside its certificate.
The projected-area check verifies predictions and errors of stored matrices,
not fitting optimality or a calibrated scattering law. Paired intervals
describe Monte Carlo repeatability for fixed scenes, and the individual
intervals are not a simultaneous multiple-comparison guarantee. None measures
real-fabric variability, physical-model discrepancy or perceptual accuracy.

