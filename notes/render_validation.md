# Independent review of the explicit-fiber renderer and camera

## Scope and conclusion

This review checks the executed 3D renderer and the conventional camera model.
It is separate from the two-dimensional exact-cylinder and ray-transport
benchmarks. No two-dimensional angular histogram is treated as a 3D material
BSDF, and these tests do not reproduce Yu et al. (2025)'s ray–wave cloth model.

The main findings are:

- Truncating multiply scattered paths at a small finite depth produces a large
  lossless white-furnace error. Unlimited depth with Russian roulette is the
  appropriate baseline for the supplied scenes.
- Unlimited-depth white-furnace radiance is close to unity, but a small measured
  deficit remains on covered pixels. The result is not exact conservation and
  is not explained away as statistical noise.
- Correct conversion of physical absorption to Mitsuba's radius-normalized
  hair parameter is required. The wrapper implements that conversion.
- The circular-pupil camera OTF agrees with an independent pupil-overlap
  calculation, and the detector model obeys its stated unsaturated photon and
  read-noise statistics.
- Pixel size is object-referred. The photon-density parameter is specified
  after optical collection. Holding it fixed across NA compares matched
  detected-photon budgets; it does not automatically model fixed-exposure
  collection efficiency.

The detailed results, uncertainty estimates, and limitations below are part of
the validation result, including when the coarse regression gates pass.

## Executed scene and numerical conventions

The validator reads the production geometry without regenerating it:
`data/fabric_plain/fibers.txt`. Its SHA-256 is
`1171b1341d7d8ce03ee9ac829b049872d2474d31280d3b9fdc579f9530b0d331`.

This is a prescribed plain weave with 10 yarns in each direction, 0.20 mm
pitch, 37 explicit fibers per yarn, 4 μm fiber radius, 16 μm lattice spacing,
0.7 turns/mm fiber twist, elliptical packing scales 1.35 and 0.60, and 0.038 mm
crimp height. The saved geometry has 24 control-point intervals per pitch.
There are 740 rendered cubic B-spline fiber curves. The geometry specifies
over/under positions and fiber trajectories; it does not solve yarn contact,
elastic equilibrium, manufacturing, or drape.

The renderer uses Mitsuba 3.9.1 / Dr.Jit 1.5.0, LLVM CPU execution with two
Dr.Jit threads, relative IOR 1.55, longitudinal roughness 0.18 and azimuthal
roughness 0.20. These are controlled model parameters, not measured constants
assigned to cotton, silk, linen, or another named textile. A Chiang-type
near-field hair BCSDF accounts for optical transport within each fiber event;
the path tracer handles subsequent intersections with other explicit curves.
No coherent phase, interference, diffraction, or polarization is propagated
by this 3D RGB path tracer.

The orthographic validation camera has a 1.64 mm field of view sampled at
96 × 96 pixels. All reported errors are computed from linear radiance before
display encoding. At approximately 17.08 μm per pixel this is an integrated
transport validation, not a claim that each 8 μm fiber diameter is resolved.

Coverage is measured through the **actual sensor's ray-generation API**, using
the pixel center and a deterministic 4 × 4 subpixel grid. The mean sampled
coverage is 0.85804579. There are 7,892 center-hit pixels, 6,574 pixels whose
16 subsamples all hit a fiber, and 768 pixels whose 16 subsamples all miss.
“Covered” below denotes the 6,574-pixel subset. This finite subpixel mask is
not a mathematical certificate of continuous pixel coverage.

Image means are the outgoing radiance observed by this camera. They are
**not** hemispherical material reflectance or transmittance. Integrating the
appropriate flux over output directions and projected area would be required
for those quantities.

## 1. Absorption units: source-level audit

The pinned source used for this audit is
[Mitsuba 3.9.1 `src/bsdfs/hair.cpp`](https://github.com/mitsuba-renderer/mitsuba3/blob/v3.9.1/src/bsdfs/hair.cpp),
included under its original BSD license in `references/Mitsuba_hair.cpp`.
The source SHA-256 is
`0ce061635989dfbb12b85b3c9f14851e858ca297ed71e8df86599b0c97a4791e`.

The internal transmitted chord in this implementation is radius-normalized:

\[
\ell^*=\frac{2\cos\gamma_t}{\cos\theta_t},\qquad
\ell_\text{physical}=r\ell^*.
\]

Consequently, to apply a physical absorption coefficient \(\mu_a\) in
mm\(^{-1}\), the shader must receive

\[
\sigma_{a,\text{shader}}=\mu_a r,
\qquad
e^{-\sigma_{a,\text{shader}}\ell^*}
=e^{-\mu_a\ell_\text{physical}}.
\]

The validator locates all three transmitted-chord expressions in the pinned
source and compares the wrapper's attenuation to Beer attenuation for radii
2, 4, and 10 μm and three transmitted-angle pairs. Agreement is at floating
point precision. This audit is source-version-specific; it must be revisited
if the hair implementation changes.

The source explicitly marks the BCSDF `NonSymmetric`. Therefore this review
does not impose a pointwise surface-BRDF reciprocity identity on that
near-field model.

## 2. White furnace and path-depth bias

The input is a constant environment radiance of one, with zero absorption.
Each condition uses 256 samples per pixel and three seeds: 9101, 9102, 9103.
Seeds are independent within each condition; the same seed set is reused
across depths. Roulette starts at depth 8. A maximum depth of -1 means no
fixed depth cutoff, with roulette termination still active.

For an ideal, lossless, conserving scene in a unit-radiance environment, the
expected output is one. Ending a path at a finite cutoff discards remaining
nonnegative transport contributions. Increasing samples per pixel does not
remove that deterministic depth-truncation bias.

| Maximum depth | Full image mean | Covered mean | Covered mean SE over three seeds |
| --- | ---: | ---: | ---: |
| 2 | 0.287045 | 0.140767 | 0.000201 |
| 4 | 0.541415 | 0.441878 | 0.000375 |
| 8 | 0.825454 | 0.786245 | 0.000276 |
| 16 | 0.972025 | 0.965850 | 0.000084 |
| 32 | 0.998093 | 0.997811 | 0.000159 |
| Unlimited + roulette | 0.998725 | 0.998578 | 0.000184 |

The unlimited-depth full-image standard error is 0.000143. The fully open
subset gives 0.999959 ± 0.000022 SE, so averaging large open regions is not
used to conceal a much darker fiber response.

The covered-pixel unlimited result is 0.1422% below one. This exceeds the
three-seed standard-error estimate. Its origin is unresolved by this review;
the combination of near-field model, numerical implementation, and rendering
estimator is not certified to conserve energy exactly. A deliberately coarse
0.7% white-furnace regression tolerance accepts this baseline while the
quantitative deficit is retained in the evidence. Passing that gate must not
be described as a zero-error physical validation.

Relative to unlimited depth, depth 8 loses 0.21233 covered radiance and depth
16 loses 0.032729. Depth 32 differs by -0.0007677. This is why the production
configuration uses unlimited depth rather than depth 8 or 16.

## 3. Illumination linearity and passive absorption

Two complementary environment maps illuminate the upper and lower world-z
hemispheres. A separate empty-scene test checks the source orientation using
the actual camera: full environment gives one, upper environment gives zero,
and lower environment gives one for rays that continue through the scene.

The upper and lower sources each use 256 spp and three independent seeds;
their seed groups are also independent of the furnace group.

| Quantity | Measured value |
| --- | ---: |
| Upper-source full-image mean | 0.250961 |
| Lower-source full-image mean | 0.748477 |
| Sum, full image | 0.999438 ± 0.000133 SE |
| Sum, covered pixels | 0.999222 ± 0.000079 SE |
| Pixel RMSE of sum versus unlimited-furnace seed mean | 0.025125 |

The covered mean of the sum exceeds the constant-furnace covered mean by
0.0006432. Both image sets contain independent Monte Carlo noise, and their
small mean discrepancies are reported rather than removed by normalization.
The experiment supports approximate source linearity at the reported error
level; it does not establish exact equality.

A separate passive case at \(\mu_a=2\,\mathrm{mm}^{-1}\), 256 spp and seed
12101 gives a full mean of 0.936043 and a covered mean of 0.923014. Absorption
reduces the response as expected. This one-seed passivity case is not used to
estimate a confidence interval or to identify a real material's absorption.

## 4. Actual illumination: Monte Carlo convergence

The convergence experiment uses the same saved cloth under the production
area-light reflection setup, with \(\mu_a=2\,\mathrm{mm}^{-1}\), unlimited
path depth, and 96 × 96 pixels. A separate 2048 spp render with seed 16001 is
the reference. The 64, 256, and 1024 spp groups each use seeds 15001–15003.
The reference is explicitly noisy, not exact ground truth.

| Samples/pixel | Full mean ± seed SE | Mean pixel RMSE to independent reference | Pixel variance × spp |
| --- | ---: | ---: | ---: |
| 64 | 0.171824 ± 0.000737 | 0.204722 | 2.570659 |
| 256 | 0.172961 ± 0.000927 | 0.105661 | 2.518541 |
| 1024 | 0.172569 ± 0.000072 | 0.062346 | 2.627890 |

The independent reference has full mean 0.172618. The RMSE standard deviations across the three seeds are 0.001968, 0.001034, and 0.000463 for 64, 256, and 1024 spp, respectively. The variance-times-spp values span only a factor of 1.0434, consistent with the expected inverse-sample variance scaling.

Despite this convergence, the 1024 spp pixel-level RMSE remains appreciable. The 192 spp production illustrations (and the 256 spp macro input) must not be treated as noiseless optical ground truth. Renderer Monte Carlo noise is already present before camera blur, pixel integration, or detector noise; increasing detector resolution cannot remove it.

For independent noisy estimates \(I_N\) and \(I_{N_r}\), a variance model
\(\operatorname{Var}(I_N)=V/N\) predicts

\[
\mathbb E\big[(I_N-I_{N_r})^2\big]
=V\left(\frac1N+\frac1{N_r}\right).
\]

The reference's noise floor is therefore included in the plotted prediction.
Between-seed pixel variance is also reported separately so agreement with a
noisy image is not the only convergence criterion. Three seeds provide a
limited estimate of uncertainty; the many spatial pixels do not turn them
into thousands of independent scene realizations.

## 5. Independent camera checks

### Pupil OTF and pixel integration

For an incoherent circular pupil, the normalized optical transfer function is
the autocorrelation area of the pupil disks. The validator computes that area
by one-dimensional numerical integration of the intersection of two unit
disks separated by \(2\nu\). It does not reuse the implementation's analytical
arccos expression. At eight frequencies the maximum absolute discrepancy is
\(6.66\times10^{-16}\).

Five two-dimensional sinusoidal gratings, including oblique gratings and
4 × 4 pixel integration, are evaluated on a 256 × 256 grid with 0.5 μm input
sampling. The independent prediction is pupil overlap multiplied by the
discrete block-average response in each axis:

\[
H_\mathrm{pixel}(k_x,k_y)=
\prod_{q\in\{x,y\}}
\frac{\sin(\pi k_q b/N)}{b\sin(\pi k_q/N)}.
\]

The zero-frequency factor is understood as one. The phase at the integrated
pixel center is included. The maximum contrast-transfer discrepancy is
\(2.78\times10^{-16}\). These tests use periodic gratings without edge padding
and resolve the optical cutoff at the input. They check the declared
diffraction-limited circular pupil; they do not validate an actual metalens,
aberration model, measured PSF, or the absence of prior aliasing in a rendered
input image.

### Detected photons and noise

The flat-field experiment uses a fixed 204.8 μm square object area, radiance
0.35 in model units, 50 detected electrons per μm² per unit radiance, 3 e⁻
read noise, and a sufficiently high full-well ceiling to avoid saturation.
It uses 64 independent seeds at each binning factor.

For effective object-referred pixel area \(A\), gain \(g=\eta A\), and
unsaturated linear radiance \(L\), the numerical detector model predicts

\[
\mathbb E[N_e]=gL,\qquad
\operatorname{Var}(\widehat L)
=\frac{gL+\sigma_r^2}{g^2}.
\]

| Binning per axis | Total expected photoelectrons | Measured/predicted per-pixel variance |
| --- | ---: | ---: |
| 1 | 734,003.2 | 1.000546 |
| 2 | 734,003.2 | 1.000115 |
| 4 | 734,003.2 | 0.997852 |

Frame-total variance ratios, estimated from only 64 totals, are 0.9633,
0.7862, and 0.7158. Those noisier aggregate estimates remain in the JSON; the
tightly determined per-pixel ratios do not justify omitting them. Mean
radiance biases are all within 1.5 predicted standard errors in this trial.

A dark, bias-subtracted readout has mean 0.0000495, negative fraction 0.4990,
and variance 0.0099748 versus predicted 0.01. Retaining negative read-noise
values prevents the positive black-level bias caused by clipping at zero.

An intentionally saturated field has saturation fraction one and collapses
to the applied ceiling. Its clipped variance is essentially zero while the
returned analytical pre-clipping variance is 3.13379. The latter is not the
variance of the clipped observation. Full-well handling here is a numerical
post-read ceiling, not a detailed charge-well and ADC electronics model.

The camera's metadata states object-referred coordinates, the after-collection
photon definition, pre-clipping variance, input and output Nyquist frequencies,
and whether each sampling grid resolves the modeled optical cutoff. Fresh
tests check those conventions. A Nyquist flag cannot repair an image that was
already aliased before entering this module. The photon coefficient is also
not an independently calibrated SI radiance-to-electron conversion or measured
multispectral sensor response.

## 6. Reproduction and evidence

From the project root, with the pinned Mitsuba and Dr.Jit dependencies:

```bash
OPENBLAS_NUM_THREADS=1 python validate_render.py --phase all
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -p test_camera.py -v
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -p test_render_physics.py -v
```

The phases `camera`, `furnace`, `sampling`, and `probe` can be run separately.
`--force` recomputes cached render cases. Use it after changing render model
code or model parameters; the existing cache keys record case settings and
geometry but are not a general source-code dependency tracker. Default
resolution is 96 and furnace spp is 256. The sampling phase deliberately
specifies 64, 256, 1024, and 2048 spp internally.

Evidence includes:

- `data/render_validation_metrics.json`: all executed case parameters,
  geometry hash, timing, means, seed uncertainty, camera and source audit.
- `data/render_validation_coverage.npz`: actual sensor-ray coverage masks.
- `data/render_validation_*.npy`: independently seeded raw linear RGB arrays.
- `data/render_validation_bsdf_probe.json`: restricted first-event sample
  weight diagnostic; reproducible with `--phase probe`.
- `data/render_validation_camera.png` and
  `data/render_validation_overview.png`: plotted numerical evidence.
- `tests/test_render_physics.py`: independent analytical and executed-data
  regression gates. The expensive renders are not repeated by test discovery.

The latest-code run completed **21 tests: 21 passed, zero failures, zero errors, zero skips** (six existing camera tests plus 15 independent physical/evidence tests). The exact test output is saved in `data/render_validation_tests.txt` and its machine-readable summary in `data/render_validation_tests.json`. All required rendering phases were complete when the evidence tests ran.

The reproducible first-event probe used 131,072 random sensor rays, of which 112,323 hit a fiber, with seed 28719. Its mean lossless `sample()` weight was 0.999999581043, standard deviation 3.9e-06, and observed range 0.999969780–1.000030756; every sampled weight was finite. This does not account for the larger whole-scene furnace deficit.

The first-event lossless probe is deliberately narrower than a furnace test.
It samples the actual first surface interactions in radiance transport mode
and reports the BCSDF `sample()` weights. Near-unit sample weights do not
independently integrate `eval()`, establish global PDF normalization, prove
pointwise reciprocity, or remove the measured whole-scene furnace deficit.

No result here establishes visual equivalence to physical cloth, real camera
color accuracy, a learned material inverse, or a metasurface advantage. Those
claims require independent measurements or separately validated optical and
inference modules.
