# Controlled Gaussian-beam extension of the exact fiber solver

This module changes one controlled physical axis: illumination. It keeps the
seven-fiber packing, circular cross sections, index, wavelength, and
polarizations fixed, and replaces the plane wave with a coherent Gaussian
angular spectrum. The aim is to determine whether beam illumination changes
the measured wave/ray discrepancy. It does not reproduce the full 2025
three-dimensional twisted-ply model or its training ensemble.

Implementation: `textile_sim/fiber_wave_beam.py`.
Tests: `tests/test_fiber_wave_beam.py`.

## Exact propagating beam and conventions

We retain the existing exp(-i omega t), host n=1, cylinder-axis z convention.
Ez and Hz are independently exact scalar reductions of the two-dimensional
Maxwell problem. The incident field is the forward-propagating angular
spectrum

\[
u_i(x,y)=\int_{-k}^{k}\frac{dq}{2\pi}\,A(q)
\exp\{i[k_x(q)(x-x_0)+q(y-y_0)]\},
\quad k_x(q)=\sqrt{k^2-q^2}>0,
\]

\[
A(q)=\sqrt\pi w_0\exp(-w_0^2q^2/4),\qquad k=2\pi/\lambda.
\]

The waist amplitude at x=x0 is exp[-(y-y0)^2/w0^2], apart from the excluded
evanescent tail. The implementation requires w0 >= 5 lambda, where that tail
is negligible; it does not extend this formula to a tightly focused vector
beam without additional work. For the executed w0=10 um and lambda=0.55 um,
k*w0/2 is about 57, far beyond the Gaussian spectrum's meaningful support.

The source is evaluated by Gauss-Hermite quadrature after q=2t/w0:

\[
u_i=\frac1{\sqrt\pi}\int dt\,e^{-t^2}
\exp\{i[k_x(2t/w_0)(x-x_0)+(2t/w_0)(y-y_0)]\}.
\]

The amplitudes of the source components are summed coherently. The distinct
source wavelengths/realizations in the earlier ensemble were instead summed
as intensities. These operations must not be confused.

## Finite beam power, not squared quadrature weights

The host scalar flux normalized to a unit-amplitude axial plane wave is

\[
j_x(x,y)=\frac1k\operatorname{Im}\big[u_i^*\partial_xu_i\big].
\]

The incident power per axial length in the corresponding normalized units is

\[
P_i=\int_{-\infty}^{\infty}j_x\,dy
=\int_{-k}^{k}\frac{dq}{2\pi}\frac{k_x(q)}k|A(q)|^2.
\]

Parseval applies to the **continuous** angular spectrum. A finite numerical
sum of plane waves is a quadrature approximation valid over a converged
spatial domain. Globally it is not a square-integrable finite-power beam.
Squaring or summing the finite plane-wave quadrature weights to define beam
power would be wrong. The code evaluates the continuous power integral with
a separate Gaussian-weight quadrature and checks it against a numerical
Poynting line integral of the explicitly reconstructed field.

At w0=10 um, lambda=0.55 um:

- exact propagating-spectrum power: **12.5326611749 um**;
- paraxial expression w0*sqrt(pi/2): approximately **12.5331413732 um**;
- the difference is the physically required longitudinal flux factor kx/k.

The ray comparison uses an untruncated Gaussian irradiance with
sigma=w0/2=5 um. It agrees with the paraxial intensity profile
exp(-2(y-y0)^2/w0^2). The exact normal flux profile has a small nonparaxial
correction, rather than being forced to equal |u|^2 point by point.

The wave angular rms in the paraxial power spectrum is about
1/(k*w0)=0.00875 rad, or 0.502 degrees. The comparison ray beam uses parallel
rays, so it does not include this finite angular spread. The Rayleigh-range
scale pi*w0^2/lambda is about 571 um, larger than the modeled cross section,
but this observation is not a substitute for a ray-direction sensitivity test.

## Coherent excitation of the already checked T-matrix

For each cylinder j and cylindrical order n, the incident regular coefficient
is

\[
c^i_{j,n}=i^n\int\frac{dq}{2\pi}A(q)
e^{i[k_x(c_{jx}-x_0)+q(c_{jy}-y_0)]}e^{-in\alpha(q)},
\quad\alpha(q)=\operatorname{atan2}(q,k_x).
\]

The same finite coupled equation is solved:

\[
b_{j,n}=t_{j,n}\left(c^i_{j,n}+\sum_{l\ne j,m}G_{jn,lm}b_{l,m}\right).
\]

`ClusterOperator` reuses `fiber_wave.cylinder_coefficients`, the checked
far-field convention, and the surface-scaled multipole system. It factors the
matrix once for a geometry/wavelength/polarization/order and permits different
beam offsets and source quadrature orders as separate right-hand sides.
The original canonical module and its saved datasets are preserved.

## Reflection, absorption, and transmission of a finite beam

The backward outgoing scattered power is

\[
P_R=\int_{\pi/2}^{3\pi/2}\frac{2}{\pi k}|F(\theta)|^2d\theta,
\qquad R=P_R/P_i.
\]

All incident components propagate forward, so the backward outgoing
hemisphere contains no outgoing incident beam. This makes the backward
scattered-field power the reflected beam power.

Absorbed power is calculated independently from the local inward boundary
flux, using the actual total local exciting coefficients c_jn:

\[
P_A=-\frac4k\sum_{j,n}\left[
\Re(c_{j,n}^*b_{j,n})+|b_{j,n}|^2\right],\qquad A=P_A/P_i.
\]

The transmitted fraction is

\[
T=1-R-A.
\]

This definition includes incident/scattered forward interference. The code
does **not** call the integral of forward-scattered intensity transmission.
For an independent flux check it also evaluates

\[
P_{\rm ext}=-\frac4k\Re\sum_{j,n}(c^i_{j,n})^*b_{j,n},
\quad
P_{\rm sca}=\int_0^{2\pi}\frac2{\pi k}|F|^2d\theta,
\]

and compares Pext-Psca with the independently calculated PA. A negative
machine-precision absorption residual for a lossless object is retained in
the raw output and interpreted as numerical roundoff, not physical gain.

## Validation and detected numerical failures

Ten named tests check:

1. The Gaussian waist field and numerical flux at x=-40, 0, +40 um.
2. Detection of inadequate source quadrature and its false far-tail power.
3. Continuum flux normalization and its paraxial limit.
4. Invalid source parameters.
5. Reduction of the reusable operator to the original plane-wave cluster code.
6. A single cylinder compared with a coherent sum of separately evaluated
   exact plane-wave scattering solutions.
7. Index matching: no scattering, A=R=0, T=1, with independently checked
   incident field power.
8. Lossless/passive absorption bounds and global/local flux agreement.
9. Simultaneous translation of beam and object.
10. Source quadrature and backward angular integration convergence.

The convergence checks detect failures rather than normalizing them away.
For example, source order 24 produces spurious field tails in a +/-60 um
line-integration window; order 64 removes them. Likewise, the optical-size
cluster's center-beam Ez backward fraction was 0.2617147 with 256-point
backward-angle quadrature and 0.2669193 with 512 points. The 512- and 1024-point
answers agree to approximately machine precision. The coarser value is
recorded as a failed angular-resolution check.

The executed benchmark checks source orders 32/64/96, multipole orders 91/99,
and backward-angle quadrature orders 256/512/1024 for every final case. The
accepted convergence gates are 1e-8 in source relative angular L2, 1e-7 in
multipole relative angular L2 and backward quadrature change, and 1e-9 in the
global/local flux discrepancy. Gates are not relaxed when a low resolution
fails.

## Experiment and artifacts

Geometry: `hex_bundle(1, radius_um=5, gap_um=.4)` from the ray implementation.
Fixed synthetic index: 1.55. Wavelength: 550 nm. Beam amplitude waist: 10 um.
Beam offsets: 0, 5, 10 um. Both Ez and Hz are evaluated. The ray calculation
uses 250,000 rays per offset/polarization and reports Monte Carlo uncertainty.

Run:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m textile_sim.fiber_wave_beam
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests -p 'test_fiber_wave_beam.py' -v
```

Artifacts: `data/fiber_wave_gaussian_beam_metrics.json`,
`data/fiber_wave_gaussian_beam.npz`, `data/fiber_wave_gaussian_beam.png`, and
`data/fiber_wave_beam_tests.log`.

This experiment supplies a controlled beam-axis comparison. It does not
resolve finite fiber length, twisted plies, broad geometry ensembles,
noncircular/birefringent fibers, real sample indices, or complete cloth
transport. Those remain separate model assumptions and validation tasks.

## Executed result: beam placement changes agreement

The following are computed backward power fractions, normalized by each
model's full incident Gaussian beam power. The ray uncertainties are one
Monte Carlo standard error; the wave calculation is deterministic.

| Polarization | Beam offset, um | Exact wave R | Ray R | Ray SE | Relative ray-wave difference |
|---|---:|---:|---:|---:|---:|
| Ez | 0 | 0.2669193 | 0.268800 | 0.0008867 | +0.70% |
| Ez | 5 | 0.2511001 | 0.244144 | 0.0008592 | -2.77% |
| Ez | 10 | 0.1932731 | 0.179728 | 0.0007679 | -7.01% |
| Hz | 0 | 0.1584708 | 0.160608 | 0.0007343 | +1.35% |
| Hz | 5 | 0.1526270 | 0.148256 | 0.0007107 | -2.86% |
| Hz | 10 | 0.1288236 | 0.110020 | 0.0006258 | -14.60% |

For the **regular geometry at the same 550 nm**, the earlier plane-wave
benchmark's backward cross-sections were 7.51135 um (wave) versus 6.83264 um
(rays) for Ez, and 4.86591 versus 4.07706 um for Hz: discrepancies of -9.04%
and -16.21%. These values come from the saved single-configuration arrays in
`fiber_wave_textile_matched.npz`, rather than the different three-wavelength,
three-geometry ensemble. The plane-wave quantities are cross-sections, not
finite Gaussian-beam R fractions; the dimensionless **relative model
discrepancy** can nevertheless be compared because its common normalization
cancels.

Changing the illumination to a centered Gaussian therefore makes integrated
backward power substantially closer for this geometry. Moving that same beam
toward the bundle edge increases the discrepancy again. This supports treating
the beam footprint and beam position as explicit experimental variables. It
does not establish a universal Gaussian-beam correction, and the small
centered differences are not exactly zero (about 2.1 and 2.9 ray standard
errors in the recorded runs).

### Integrated R agreement is insufficient for appearance

For the centered beam, after **identical two-degree binning over the backward
hemisphere**, the wave/ray angular-intensity relative L2 discrepancy is still
**0.4811 (Ez)** and **0.5433 (Hz)**. The corresponding relative L1 discrepancies
are **0.4716** and **0.4834**. Across the three beam offsets the angular L2
discrepancies remain approximately 0.48-0.55.

Thus two models can give nearly the same total reflected power while
distributing it differently with angle. This is directly relevant to cloth
appearance: an R/T-only validation cannot establish correct directional
gloss, highlights, or camera-view response. The present coherent monochromatic
fringes also require explicit spectral, angular, spatial, and geometry
averaging before any claim about ordinary product photography.

This distinction is shown in
`data/fiber_wave_gaussian_backward_profiles.png`. The beam-offset R comparison
is in `data/fiber_wave_gaussian_beam.png`.

### Final numerical checks

Across all six cases:

- numerical incident line flux versus the continuum spectral power, using
  at least 64 source nodes: relative discrepancy <= **4.26e-16**;
- N=91 versus N=99 scattered angular intensity: relative L2 <= **4.94e-10**;
- source quadrature 64 versus 96: relative L2 <= **3.28e-15**;
- backward quadrature 512 versus 1024: relative change <= **2.75e-14**;
- independently calculated global versus local absorption flux: relative
  discrepancy <= **3.10e-15**.

The lossless absorption residues are around -5e-14 to -7e-14 of incident power
and are retained as floating-point residuals. They are not interpreted as
negative absorption. All ten dedicated beam tests pass.
