# Independent scientific and implementation review — v0.3

Review date: 2026-10-11. The reviewer authored the tests below separately from the mechanics and optical modules, read the new source, constructed counterexamples, and recomputed selected saved experiment statistics. Primary literature and reading-file hashes are recorded in [the v0.3 literature note](literature_engine_v3.md).

## 1. Assessment

v0.3 makes a material improvement over a purely prescribed weave: a declared yarn-height energy is minimized under explicit geometric inequalities, and the resulting hierarchy is compared optically using the same physical observation rig. The strongest achieved result is an auditable connection from **reduced yarn equilibrium → regenerated explicit fibers → directional geometric statistics and spectral ray rendering**.

This is a credible research scaffold within its stated domain. It is not a complete rod/contact solver, a mass-conserving fiber deformation model, a full fabric BSDF obtained from a tensor, or a validated prediction of silk/cotton/cupra appearance. The synthetic experiments do not establish an advantage over a good multi-light RGB acquisition system or justify a fabricated metasurface yet.

Three concrete review findings were fixed before this review's final tests. Two could otherwise have produced plausible but unsupported numerical claims: an apparently successful angular fit from unidentifiable data, and an equilibrium certificate attached to the wrong geometry/problem.

## 2. Findings, fixes and regression evidence

| Finding | Actual counterexample or failure | Implemented response | Independent regression |
| --- | --- | --- | --- |
| R1: Angular fit success did not imply identifiability | Twenty repeated observations along one axis gave a tiny training residual and `fit_success=True`, despite failing to identify six independent coefficients of a three-dimensional symmetric tensor. | Reject weighted quadratic-design rank below six; record rank and condition number. | Duplicate directions and a coplanar circle are both rejected. |
| R2: Export trusted a stale equilibrium diagnostic | Replacing the solved heights with the feasible initializer still exported as KKT-certified. Passing the same result to a same-sized problem with 20 times warp bending stiffness also passed. | Bind a result to the complete problem specification and height-state SHA-256; recompute KKT, feasibility and energy gates at export; export the recomputed diagnostic. | Both stale-state and wrong-problem exports now raise. Changing the old diagnostic dictionary cannot substitute a fabricated KKT record. |
| R3: A configured slope bound was reported outside its domain | An off-crossing height perturbation can violate the declared maximum slope while preserving crossing order. Its clearance estimate cannot use the smaller configured Lipschitz constant. | Gate the configured clearance bound on its slope premise and report a separate bound using observed maximum slopes of each family. | The invalid configured certificate becomes `None`; observed-slope diagnostic remains available; infeasible geometry export raises. |

For R2, before the fix, the substituted initializer had actual normalized stationarity residual approximately **8.90 × 10⁻⁴**, while the exported stale value was approximately **3.84 × 10⁻¹¹**. Applying the solved state to the changed-stiffness problem gave approximately **2.65 × 10⁻³**. These were actual evaluations of `equilibrium_residual`, not hypothetical malformed-input descriptions. The repaired export prevents this scientific provenance error.

The ordinary mutable diagnostic dictionary is now supplementary information. The important state is checked again when it becomes geometry used by the optical engine. This is a numerical integrity measure; it does not purport to defend against arbitrary malicious reconstruction of all Python objects.

## 3. Independent test suite

Command:

```bash
python -m unittest discover -s tests -p test_v3_independent_review.py -v
```

The recorded run completed **12 tests, all passing, in 2.291 seconds**. These tests supplement the implementers' suites rather than replacing them.

| Independent test | What it constrains |
| --- | --- |
| Equal tangent covariance / different projected area | Higher-order directional information cannot be recovered from the second moment alone. |
| Projection additivity, subdivision and geometric scaling | Splitting a straight segment cannot change its total contribution; groups sum under the same volume; mm⁻¹ scales correctly. |
| Rank-deficient angular acquisition | More samples do not cure absent three-dimensional angular information. |
| SGGX joint rotation and density scaling | Coordinate-frame changes preserve predictions; scaling the area density scales the NDF but not the normalized phase. |
| SGGX matrix mixture counterexample | Arithmetic tensor interpolation is not an exact linear mixture of projected areas. |
| Exactly integrable spectral fixture | Nonuniform render wavelengths with an affine response integrate correctly against a synthetic constant observer/source; truncated spectral mass is accounted for. |
| Pinned-beam sine eigenmodes | The discrete boundary stencil and axial/bending coefficients match an independent analytic spectrum. |
| Nonlinear energy/force/Hessian dimensional covariance | A geometry/stiffness similarity transform gives the expected energy, force and Hessian units. |
| State/problem-bound equilibrium export | Geometry cannot inherit another state or problem's equilibrium assertion. |
| Recomputed export KKT | A mutable diagnostic dictionary is not accepted as numerical evidence. |
| Invalid slope certificate | A distance bound is conditional on its actual Lipschitz premise. |
| Rectangular asymmetric family exchange | A 3 × 2 weave with different pitches, radii, stiffnesses and initialization shares is physically unchanged by correctly swapping families and coordinates. |

The rectangular family test uses `draft.transposed()`, which complements and transposes the crossing bits. A plain matrix transpose would invert physical over/under order when the meaning of warp changes. This check is stronger than a square symmetric plain-weave example.

## 4. Mechanics review

### 4.1 Constitutive mathematics and units

For a height difference \(d\), fixed projected interval \(h\), and rest interval \(\ell_0\le h\), exact extension uses \(\ell=\sqrt{h^2+d^2}\). Its first and second derivatives were checked from the scalar energy independently of the source implementation:

\[
E_s'(d)=\frac{EA}{\ell_0}\left(1-\frac{\ell_0}{\ell}\right)d,
\qquad
E_s''(d)=\frac{EA}{\ell_0}\left(1-\frac{\ell_0 h^2}{\ell^3}\right)\ge0.
\]

The nonnegative Hessian follows from the restricted tension domain. Together with the quadratic small-slope bending energy and linear constraints, it defines a convex finite-dimensional problem. No contact/friction nonconvexity or compression/buckling behavior has been solved by imposing that restriction.

| Quantity | Unit |
| --- | --- |
| Coordinates, rest lengths | mm |
| Effective axial stiffness \(EA\) | N |
| Effective bending stiffness \(B\) | N mm² |
| Energy | N mm |
| Nodal energy gradient | N |
| Height Hessian | N/mm |

At a flat state with \(n\) interior samples, the pinned discrete sine mode \(v_j=\sin(k\pi j/(n+1))\) has difference-Laplacian eigenvalue \(\mu_k=4\sin^2(k\pi/(2(n+1)))\). The tested stiffness eigenvalue is

\[
\lambda_k=\frac{EA(1-r)}{rh}\mu_k+\frac{B}{h^3}\mu_k^2,
\qquad r=\ell_0/h.
\]

This separately checks boundary behavior and both energy coefficients. Scaling every height and interval by \(a\), with \(B\mapsto a^2B\) and fixed \(EA,r\), gives \(E\mapsto aE\), \(g\mapsto g\) and \(H\mapsto H/a\); finite-amplitude tests verify all three.

### 4.2 Meaning of equilibrium and clearance

The optimizer success flag is not sufficient. The module independently estimates nonnegative active inequality multipliers and reports stationarity, complementary slackness and feasibility. These are numerical residual gates for the discretized, declared model. They are not a rigorous interval-arithmetic global error bound, a bound on distance to a continuum solution, or a physical validation against a textile.

The crossing/slopes argument gives a genuine geometric lower bound for the prescribed piecewise-linear orthogonal tracks. If signed crossing separation is positive and the two height graphs have Lipschitz constants \(L_w,L_f\), then

\[
d_{\min}\ge\frac{D}{\sqrt{1+L_w^2+L_f^2}}.
\]

Subtracting the two declared envelope radii gives an envelope-clearance bound. Parallel families require their separate pitch bound. Neither bound supplies contact pressure, a friction law, flattening, or the actual cross-sectional material response. The independently tested state export and the subsequent explicit-fiber clearance audit serve different purposes.

The bending term is small-slope Euler–Bernoulli bending. The reported factor involving \((1+L^2)^{5/2}\) compares continuum graph integrands under a slope bound; it is not a general discrete-curvature error bound. The source now states this explicitly.

### 4.3 Constituent-fiber limitation

The hierarchy is regenerated on the new yarn tracks, with twist measured per current arc length. Stable IDs do not establish material-point, strain or volume conservation. In the optical comparison fixture, the saved line-element lengths change by:

| Group | Relative length change |
| --- | ---: |
| All fibers | +0.044242% |
| Warp fibers | −0.573576% |
| Weft fibers | +0.662060% |

Radii stay fixed, so represented cylindrical-volume changes have the same fractions in this fixture. The small total change does not eliminate family-level redistribution. Optical differences must therefore be attributed to the complete regenerated geometry, not exclusively to an isolated change of tangent distribution.

## 5. Optical review and saved-output audit

### 5.1 Hierarchical geometric reduction

The projected-area target is an additive, unoccluded line-element statistic with declared common averaging volume. It does not account for overlapping projected silhouettes, occlusion, spatial correlations, endcaps, inter-fiber multiple scattering or wave interference. Fitting SGGX to it is a geometric compression experiment, not an automatic derivation of a fabric BSDF.

The saved experiment uses 96 training directions and 1,200 distinct held-out directions. The nearest train/test pair has dot product approximately 0.9999599984; there are no identical directions. This is held-out interpolation on the same synthetic geometry, not an unseen-fabric or unseen-manufacturing-process evaluation. RMSEs were recomputed directly from saved prediction and target arrays:

| State | One tensor, 6 parameters | Two family tensors, 12 parameters | Six yarn tensors, 36 parameters | Six ply tensors, 36 parameters |
| --- | ---: | ---: | ---: | ---: |
| Initial | 3.5727% | 0.21976% | 0.21976% | 0.21976% |
| Relaxed | 3.5788% | 0.29841% | 0.29897% | 0.29897% |

The improvement comes from retaining the two directional families. More parameters do not improve this particular test. The relaxed yarn fit is slightly worse than the family fit, and each yarn has one ply, making yarn/ply predictions identical. This fixture does not demonstrate a separate advantage of ply-scale optical compression. The multi-ply mechanics fixture is a different experiment.

The equal-second-moment counterexample and the Jensen matrix-mixture inequality in the literature note are analytic representational limitations. They should not be advertised as new discoveries of SGGX theory or as evidence that two sample photographs are indistinguishable.

### 5.2 Actual spectral rendering

The driver executes 536 explicit-fiber monochromatic ray renders: two states × three source directions × 17 wavelengths × four independent seeds, plus two states × 16 midpoint wavelengths × four seeds for one reflection direction. A separate Lambertian run checks finite-source radiometry.

The optical engine uses the declared synthetic material spectra, actual fiber curves, fixed source/camera coordinates and the same material IDs/radii in both states. The scalar wavelength sweep uses real Fresnel indices with absorption in the existing hair transport model; it does not evaluate coherent fields, polarization, fluorescence or a measured camera sensor. The output observation uses the official CIE 1931 observer with normalized Planck sources. Planck 6500 K is not the CIE D65 spectrum. Display images use a fixed exposure and no chromatic adaptation.

The saved images were independently reduced in float64, and the paired mean differences and Student-t intervals recomputed without the module's paired-interval helper. The values agree with the stored metrics within a 10⁻⁷ radiance accumulation budget. Replicates are the four independent seeds; correlated pixels and wavelengths are not counted as independent samples.

| Source direction | Planck source | Relative mean Y change | 95% paired-seed interval for absolute ΔY |
| --- | ---: | ---: | --- |
| Reflection, azimuth 0° | 3000 K | +36.69% | [0.003711, 0.008103] |
| Reflection, azimuth 0° | 6500 K | +37.04% | [0.003833, 0.008046] |
| Reflection, azimuth 90° | 3000 K | −33.42% | [−0.006360, −0.004059] |
| Reflection, azimuth 90° | 6500 K | −32.37% | [−0.006447, −0.004034] |
| Transmission, azimuth 45° | 3000 K | +1.00% | [−0.000329, 0.000501] |
| Transmission, azimuth 45° | 6500 K | +0.64% | [−0.000422, 0.000535] |

Thus this chosen geometry modification changes the mean response in opposite directions under the two reflection sources. The small transmission change is unresolved at this Monte Carlo budget. These intervals characterize Monte Carlo repeatability only. Four seeds are not enough to validate a general sampling distribution, and the intervals exclude model, calibration, geometry and spectral-discretization errors. They are neither perceptual confidence intervals nor predicted uncertainty for real fabrics.

### 5.3 Numerical errors and remaining limits

For the azimuth-0° reflection source, actual 12.5 nm midpoint renders reduce the nested-grid step size. The relative mean XYZ differences between the 25 nm and 12.5 nm grids are:

| State | 3000 K | 6500 K |
| --- | ---: | ---: |
| Initial | 0.17045% | 0.23207% |
| Relaxed | 0.36112% | 0.36314% |

This comparison supports limited spectral-grid stability for that source and fixture; the finer image still contains Monte Carlo error and is not an exact spectral reference. Other source directions were only compared at 50/25 nm. The source photopic mass outside 380–780 nm is approximately 4.53 × 10⁻⁶ and 4.14 × 10⁻⁶ for the two normalized Planck examples, as reported by the observer integration. This is a source/observer mass diagnostic, not a universal bound on an arbitrary omitted material response.

The independent 100 × 100 quadrature for a diffuse reference predicts center radiance 0.25205344; the separate renderer's central 2 × 2 pixel mean is 0.25250250, a relative difference of 0.17816%. Finite pixel footprint and Monte Carlo noise remain in that comparison. This checks the observation rig and normalization, not the accuracy of the fiber BSDF.

The source explicit-fiber gap lower bounds are 2.9836 and 2.9454 μm. Subtracting both curves' worst declared spline/float32 displacement allowances leaves positive lower bounds of 2.8354 and 2.5976 μm for different fibers after export. A geometric displacement bound does not translate automatically into a radiance bound, especially near glints or visibility transitions. No image-error certificate is claimed.

## 6. Source snapshot and reproducibility

The independent suite above was run against these source snapshots:

| File | SHA-256 |
| --- | --- |
| `textile_sim/weave_mechanics.py` | `cf362e8106c6d2ec3af552d8ab399fe87dd20ac291bee50633b30e0b8fdeb94a` |
| `textile_sim/optical_lod.py` | `17b84759aa734e07e4d9c9ef3108cf537c69305a3836674a044e033160fc0519` |
| `tests/test_v3_independent_review.py` | `d1610f4a9d6cf0bc1c4681649440522d6ce9e2fccf3d612f9d7f3cefbed8e1ea` |
| `run_multiscale_optics_v3.py` | `2fe34e8a5c98b64c3697a07e96bd847dfcd28e2199f5a50a9f35bb4cbbee9bdd` |
| `data/optical_v3/optical_scale_metrics.json` | `e23460870d43f4c75369430fd2c64b3d50b994248a5c0d04428a1fd546bccead` |

The final optical run's four recorded source hashes were independently checked against the current files and all matched. The input mechanics pair-metrics hash also matched. The optical driver records its source hashes and asserts they are unchanged during an experiment. Raw wavelength stacks, geometry manifests, exact seeds, observer data, fit predictions, and parameter records accompany the metrics in `data/optical_v3`. The final repository validation should additionally verify that those recorded hashes match the final checked-in source. Later source changes require a new test/experiment record; a previous passing result is not evidence for an untested file.

The mechanisms reviewed here have clear next scientific gates: mechanical calibration and material-coordinate transport; more difficult mixed-ply/irregular fiber geometries; visible appearance comparison with measured fabrics; and a strong RGB acquisition baseline. Measurement/metasurface design should then target ambiguities that remain under those controls. The present implementation enables those tests but has not completed them.

## 7. Integration follow-up: family-exchange convergence gate

The first full 230-test run at `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` reported one failure in the rectangular family-exchange comparison. The maximum coordinate difference was 4.7684e-9 mm (about 4.77 pm); the geometric test used 3e-9 mm absolute tolerance. Independently permuting a perturbed height vector gave zero gradient/Hessian difference and 1.69e-21 N·mm energy difference, establishing equation covariance separately from optimizer termination.

The regression was strengthened with those energy/gradient/Hessian checks and now requests a tighter stationarity tolerance of 1e-10 for the two compared optimizations. The coordinate assertion was **not loosened**. The difference fell to 6.886e-11 mm and the relative energy difference was 1.44e-15. Both independent KKT checks passed even though SLSQP itself reported precision-related failure status; acceptance continues to depend on the independently recomputed residual, feasibility and energy gates. All 12 independent review tests then passed in 4.578 s. The scientific mechanics/optical modules and recorded 536-render experiment were unchanged.

The original failing run is retained in [initial_full_suite_failure.json](../data/validation_v3/initial_full_suite_failure.json). The diagnosis, stricter tolerance and revised test source hash are recorded in [family_exchange_followup.json](../data/validation_v3/family_exchange_followup.json). The historical source table in §6 identifies the earlier independent-review snapshot; the final source hash and complete suite count are authoritative in [final_test_summary.json](../data/final_test_summary.json).
