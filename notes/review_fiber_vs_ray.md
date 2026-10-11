# Independent review: power-ray module and its exact-wave interface

Reviewer: implementer of the independent `fiber_wave.py` Maxwell module.
Reviewed implementation: `textile_sim/ply_ray.py`, including Fresnel
coefficients, circle intersections, event handling, absorption, statistics,
and the analytic single-cylinder ray-order reference. The implementation and
its tests were read; additional independent checks were executed and saved to
`data/fiber_wave_review_ray.json`.

## Findings

No critical algebraic, direction-sign, or energy-accounting defect was found
within the stated model: two-dimensional circular, isotropic fibers; real-index
Fresnel interfaces; optional Beer attenuation along internal ray segments.

1. **Polarization and refraction signs agree with the wave convention.**
   Propagation is +x at zero incidence; output is atan2(dy, dx). Ez corresponds
   to s polarization and Hz to p polarization. The transmitted direction
   `eta*d + (eta*cos_i-cos_t)*normal` uses a normal opposing incidence, including
   the reversed normal when exiting a cylinder.
2. **The interface roulette follows power, not field amplitude.** The probability
   R uses the squared Fresnel amplitude. Selecting reflection with probability R
   and transmission with probability 1-R without changing the ray's weight is
   correct for power sampling. An extra factor n*cos(theta) must not then be
   multiplied into this already power-conserving roulette.
3. **Internal attenuation is evaluated on actual chord lengths.** Absorbed power
   is accumulated as the previous weight minus the attenuated weight. A ray
   stopped by the event limit retains its unprocessed power in the residual.
   It is not mislabeled as escaped light. An internal intersection failure
   similarly remains a reported residual.
4. **Angular Monte Carlo standard errors are consistent with weighted samples.**
   The histogram uses the sample second moment and subtracts the squared mean;
   the denominator is N(N-1) for the variance of the estimated mean. Different
   angular bins are correlated; per-bin errors should not be summed in
   quadrature to obtain an integrated backward-power error. The matched
   benchmark uses the separately calculated backward-channel standard error.
5. **The single-cylinder analytic ray reference is an independent useful check.**
   For impact angle i and refracted angle r, external reflection has deflection
   pi-2i. An exit after p internal chords has deflection
   `(p-1)*pi - 2*i + 2*p*r` and weight proportional to
   `(1-R)^2 R^(p-1) exp(-mu*2*a*p*cos(r))`. These match the vector ray tracer's
   orientation and count one internal chord before the first exit.

## Additional checks executed by this reviewer

### Heterogeneous absorbing seven-fiber cluster, index matched

The refractive index was set equal to the host, so every trajectory is a
straight line even though it can cross several circles. The absorption
coefficients were different for every fiber:

`[0.002, 0.007, 0.021, 0.017, 0.032, 0.008, 0.025] um^-1`.

For a ray at transverse coordinate b, the independent analytic prediction is

\[
\ell_j(b)=2\sqrt{\max(0,a_j^2-(b-y_j)^2)},
\qquad w(b)=\exp[-\sum_j\mu_j\ell_j(b)].
\]

This formula does not use the tracer's intersections, event state, or recorded
segment lengths. Fifty thousand rays were generated with a 40 um uniform beam
and seed 88431. The maximum absolute disagreement was:

- final ray weight: **1.6653e-15**;
- total internal path length: **1.2218e-13 um**;
- numerical intersection failures: **0**.

Adaptive one-dimensional quadrature of w(b) across the beam gave a transmitted
fraction of **0.8130470357**. The Monte Carlo result was **0.8143498613**, with
standard error **0.0005954405**; the difference was **2.188 standard errors**.
The deterministic per-ray equality and the aggregate stochastic check are
separate tests.

### Length scaling

For 8000 identically seeded rays (seed 117), multiplying every center and
radius by 1000 preserved all escaped/absorbed/residual channel fractions
exactly in the recorded run. The largest output-angle difference was
**1.1862e-12 rad**. This checks that micrometer units do not enter a lossless
geometric-optics result except through dimensionless geometry.

### Refractive-index ratio scaling

Multiplying both host and fiber index by 1.33 preserved the same ray angles
and channel fractions exactly in the recorded run. The original pair was
(1, 1.55), and the scaled pair was (1.33, 2.0615). This is the correct
dependence for the tested lossless nonmagnetic geometric Fresnel/Snell model.

## The wave-ray connection that is valid here

`fiber_wave.run_textile_benchmark()` obtains centers and radii by directly
calling `ply_ray.hex_bundle(shells=1, radius_um=5, gap_um=.4)`. Thus the optical
size, arrangement, fixed index n=1.55, polarization, angular origin, and beam
projection are matched. The regular configuration's projected width is about
28.0133 um. The wave solver uses a plane wave; the ray beam covers the full
projected object width, so every geometrically contributing ray is included.

The comparison uses absolute differential cross-sections in um/rad. Wave
intensities are integrated into the same two-degree bins as the ray histogram.
The central +/-6 degrees are excluded from the **reported off-forward shape
error**, because the ray model has no forward diffraction term. They remain
visible in the raw full-angle data and plots. No intensity, energy, or angular
shape is rescaled to force agreement.

The incoherent ensemble uses three wavelengths (450, 550, 650 nm) and three
geometries (the regular packing and two displacements with standard deviation
0.06 um), with equal weights. Rays are evaluated for the same three geometries;
their index and geometry have no wavelength dependence in this fixed-index
benchmark. This is a deliberately small ensemble. It is not the cloth paper's
beam, three-dimensional twist, 50-geometry training ensemble, or fitted noise
model. Agreement or disagreement is reported from the actual data.

Every wave ensemble member is checked by comparing maximum multipole orders
N and N+8. If relative angular-intensity L2 change exceeds 1e-7, the order is
increased by another eight while preserving the failed comparison in the
metrics. A jittered 450 nm case did trigger this gate; a conservation-only test
would not have detected its truncation error. This is a numerical correction,
not a relaxation of the requested tolerance.

## Limits that matter for interpretation

- Ray `encountered` counts a geometrical boundary hit. An index-matched circle
  has such hits but has zero Maxwell scattering. The code's distinction is
  necessary and correct.
- The ray angular cross-section integrates to geometrically intercepted
  power. Exact Csca is the cross-section of the scattered **field**, and Cext
  includes incident/scattered forward interference. They cannot be equated or
  combined by simply adding the wave scattered intensity to an unmodified
  ray-transmitted beam.
- Real-index Fresnel plus Beer attenuation is a weak-absorption approximation.
  It is not the exact complex-index boundary problem. For a future quantitative
  comparison, relate the absorption coefficient to kappa by
  `mu = 4*pi*kappa/lambda` and check whether neglecting kappa in the interface
  Fresnel coefficients is acceptable for that regime.
- Neither solver resolves finite fiber length, a twisted three-dimensional
  ply, noncircular or rough surfaces, birefringence, or measured textile
  chemistry. This review certifies the stated implementation checks and
  records the interface contract; it does not establish real-fabric accuracy.

Reproducible benchmark commands from the `textile_lab` directory:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m textile_sim.fiber_wave --textile-benchmark
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests -p 'test_ply_ray.py' -v
```

Detailed results are in `data/fiber_wave_textile_matched_metrics.json` and
`data/fiber_wave_review_ray.json`. The numerical values above are actual
executed review observations, not target specifications.

## Matched benchmark outcome

The full ensemble completed with maximum accepted multipole relative L2 change
9.1889e-8 and maximum global/local flux mismatch 9.9454e-15. The complete
wave/ray run took 67.72 seconds in the observed shared execution environment.
Using the predeclared +/-6 degree exclusion, the angular relative L2 errors
were 0.5064 (Ez) and 0.5465 (Hz). The backward cross-section was underestimated
by the geometric power model by 7.55% and 23.99%, respectively; the reported
Monte Carlo uncertainty is much smaller than these differences.

This result does not support substituting the geometric ray kernel for the
exact wave kernel at the tested two-degree resolution and small ensemble.
The two solvers can each be correct within their own equations while their
predictions differ. The physical approximation and source/geometry averaging
must therefore remain explicit in any higher-level cloth model. Nothing in
this test establishes that a metasurface would improve real-fabric capture.
