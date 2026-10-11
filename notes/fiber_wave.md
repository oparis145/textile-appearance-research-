# M1: exact two-dimensional electromagnetic fiber and bundle module

## What was implemented

`textile_sim/fiber_wave.py` is original Python/NumPy/SciPy code. It solves the
Maxwell boundary-value problem for an infinitely long circular dielectric
cylinder, and the coupled problem for a finite set of parallel, nonoverlapping
cylinder cross-sections. It also evaluates the complex field inside and
outside a cluster. No third-party solver code was copied.

The finite cluster includes repeated electromagnetic interaction among the
cylinders through a dense multipole linear system. It is more than an
independent sum of single-fiber scattering patterns. It is nevertheless **two
dimensional**: the cylinders remain infinite and parallel along their axes.
A seven-cylinder cross-section is not a resolved three-dimensional twisted
yarn, and the synthetic index used here is not a measured silk/cotton value.

Primary mathematical references consulted:

1. K. Watanabe, Y. Nakatake and J. Pištora, *Accurate analysis of electromagnetic
   scattering from periodic circular cylinder array with defects*, Optics
   Express 20(10), 10646-10657 (2012),
   <https://doi.org/10.1364/OE.20.010646>. Its cylindrical transition matrix and
   translation formulation are relevant; we implement a **finite nonperiodic
   cluster**, not its periodic-defect solver. The publisher's indexed equation
   text was accessible; the live article HTML returned a waiting page.
2. NIST Digital Library of Mathematical Functions, §10.23, especially Graf's
   addition theorem: <https://dlmf.nist.gov/10.23>.
3. T. M. Dunster, *Electromagnetic Wave Scattering by Two Parallel Infinite
   Dielectric Cylinders*, Studies in Applied Mathematics 131(3), 302-316 (2013),
   <https://doi.org/10.1111/sapm.12014>. The publisher abstract confirms the
   coupled Hankel/Bessel representation; its full text was not used to claim
   reproduction.

The cited 2025 cloth ray-wave paper motivates multiscale modeling, but this
module does **not** reproduce its Gaussian-beam ply simulator, fitting, noise
calibration, or three-dimensional rendering method.

## Conventions and units

- Lengths: micrometers; vacuum/host wavelength: `wavelength_um`.
- Host refractive index: 1; relative magnetic permeability: 1 everywhere.
- Passive dielectric index: `n_complex = n + i*kappa`, with n > 0 and kappa >= 0.
- Time convention: exp(-i omega t), so Hankel functions of the first kind are
  outgoing.
- Cylinder axis: z. Illumination propagation and observation directions lie
  in the x-y plane; theta = 0 is +x.
- `Ez`: electric field parallel to z. `Hz`: magnetic field parallel to z.
  These explicit component labels avoid inconsistent TE/TM naming conventions.
- Cross-sections Csca, Cext, Cabs: micrometers, i.e. scattering cross-section
  **per unit axial length**. Differential cross-section: micrometers/radian.

## Single-cylinder boundary solution

Let k = 2 pi / lambda, x = k a, m = n_complex, and alpha the incident
propagation angle. For a unit scalar incident field,

\[
u_{\rm inc}(r,\phi)=e^{ikr\cos(\phi-\alpha)}
=\sum_{n=-\infty}^{\infty}i^n e^{-in\alpha}J_n(kr)e^{in\phi}.
\]

The outgoing field uses the same incident modal phase times t_n H_n^(1).
Define gamma = m for Ez and gamma = 1/m for Hz. Field and weighted normal
derivative continuity give

\[
J_n(x)+t_nH_n^{(1)}(x)=q_nJ_n(mx),
\qquad
J'_n(x)+t_nH_n^{(1)\prime}(x)=\gamma q_nJ'_n(mx).
\]

Consequently,

\[
t_n=\frac{\gamma J'_n(mx)J_n(x)-J'_n(x)J_n(mx)}
{H_n^{(1)\prime}(x)J_n(mx)-\gamma H_n^{(1)}(x)J'_n(mx)},
\]

\[
q_n=\frac{J_n(x)H_n^{(1)\prime}(x)-J'_n(x)H_n^{(1)}(x)}
{H_n^{(1)\prime}(x)J_n(mx)-\gamma H_n^{(1)}(x)J'_n(mx)}.
\]

For Ez the derivative condition comes from continuity of the tangential
magnetic field with equal permeability. For Hz the derivative is weighted by
inverse permittivity, giving gamma = 1/m. Choosing this factor incorrectly
would exchange or corrupt the polarization responses.

The large-distance field convention is

\[
u_s\sim\sqrt{\frac{2}{\pi kr}}\,
e^{i(kr-\pi/4)}F(\theta),\qquad
F(\theta)=\sum_n t_n e^{in(\theta-\alpha)}.
\]

The cross-sections are

\[
\frac{dC_{\rm sca}}{d\theta}=\frac{2}{\pi k}|F(\theta)|^2,
\quad C_{\rm sca}=\frac4k\sum_n|t_n|^2,
\quad C_{\rm ext}=-\frac4k\Re\sum_n t_n,
\quad C_{\rm abs}=C_{\rm ext}-C_{\rm sca}.
\]

The minus sign in extinction follows this t_n convention; a common alternative
coefficient is a_n = -t_n. Each lossless retained mode obeys
Re(t_n) = -|t_n|^2. This modal identity alone does not certify a sufficient
truncation order. A severely truncated lossless expansion can still conserve
power while predicting the wrong angular pattern.

An independent small-size check uses

\[
Q_{\rm sca}^{E_z}\sim\frac{\pi^2}{8}(m^2-1)^2x^3,
\qquad
Q_{\rm sca}^{H_z}\sim\frac{\pi^2}{4}
\left(\frac{m^2-1}{m^2+1}\right)^2x^3,
\qquad Q_{\rm sca}=\frac{C_{\rm sca}}{2a},
\]

for real m, x approaching zero. The test evaluates x = 0.002 and requires
agreement within 1e-4 relative error.

## Exact parallel-cylinder coupling

For cylinder j at center c_j, let c_{j,n} be its total regular incident
coefficient and b_{j,n} its outgoing Hankel coefficient. Plane-wave excitation
is

\[
c_{j,n}^{\rm plane}=e^{ik\hat d_\alpha\cdot c_j}
i^n e^{-in\alpha}.
\]

For j different from l, with R = c_j-c_l and beta = arg(R), Graf translation
gives

\[
G_{jn,lm}=H_{m-n}^{(1)}(k|R|)e^{i(m-n)\beta}.
\]

The coupled equations are

\[
b_{j,n}=t_{j,n}\left(c_{j,n}^{\rm plane}
+\sum_{l\ne j}\sum_mG_{jn,lm}b_{l,m}\right).
\]

The implementation solves for surface-scaled unknowns
u_{j,n} = H_n^(1)(k a_j) b_{j,n}. This is an invertible change of variables,
not regularization, loss, or energy renormalization. It reduces the enormous
dynamic range of high-order Hankel coefficients. The linear solve retains all
orders of repeated interaction represented by the truncated basis.

The cluster far field is

\[
F(\theta)=\sum_{j,n}b_{j,n}(-i)^n e^{in\theta}
e^{-ik\hat d_\theta\cdot c_j}.
\]

Extinction follows the forward amplitude,
Cext = -(4/k) Re F(alpha), while scattering is independently integrated over
the full outgoing azimuth. A third, independent energy accounting uses local
boundary flux:

\[
C_{\rm abs}^{\rm local}
=-\frac4k\sum_{j,n}
\left[\Re(c_{j,n}^* b_{j,n})+|b_{j,n}|^2\right].
\]

We report both Cext-Csca and this local absorption sum, and their discrepancy.
We never set scattering equal to extinction minus absorption. No negative
floating-point absorption residues are silently clipped.

## Incoherent illumination and the integration contract

Independent wavelengths and source directions add **intensities**, not complex
amplitudes:

\[
\left\langle\frac{dC}{d\theta}\right\rangle
=\sum_{\lambda,\alpha}w_\lambda w_\alpha
\frac{2}{\pi k_\lambda}|F_{\lambda,\alpha}(\theta)|^2.
\]

Weights in this module are incident-irradiance fractions normalized to one.
The demonstration's uniform wavelength samples are an explicit synthetic
source model, not a daylight spectrum or a colorimetric RGB integration.

**Do not use Csca as a reflection/transmission probability.** Cross-sections
can exceed a cylinder's geometric width without violating conservation.
Extinction contains interference of incident and forward-scattered fields.
An unchanged geometric transmitted component cannot be added to the exact
wave scattered field's intensity to create a conservative BSDF. Any future
ray-wave interface must define a finite incident beam or another consistent
flux normalization and handle the direct/forward interference component.

Likewise, the coherent seven-fiber solution is a benchmark for the local
parallel-cross-section problem, not a cloth-wide BSDF that can be blindly
replicated over a woven surface. Twist, finite length, oblique propagation,
noncircular fiber shape, surface roughness, birefringence, and measured optical
dispersion require additional modeling.

## Implemented experiment matrix

- Single-cylinder size parameter: 100 logarithmic samples from 0.01 to 150,
  both polarizations, synthetic lossless n = 1.53.
- Resolved angular patterns: radius 5 um, 550 nm, versus intensity averaging
  over 15 wavelengths from 450 to 650 nm and 9 incident angles from -3 to +3
  degrees. This separates spatially coherent fine fringes from a controlled
  broad-source/broadband average.
- Coupled cluster: seven fibers of radius 0.35 um, one at the origin and six
  on a radius-1 um ring, both polarizations, 550 nm. Compared with coherent
  superposition of isolated-fiber amplitudes with inter-fiber coupling omitted.
- Disorder perturbation: independently seeded Gaussian center displacements
  with standard deviation 0.045 um; actual disjointness is checked.
- Cluster multipole orders N = 4, 6, 8, 10, 14, 18, 22, 26; the angular pattern
  and cross-sections are compared, not conservation alone.
- A passive cluster with n = 1.53 + 0.02i checks global and local absorption.
- Spatial complex Ez map for the coupled cluster; the plotted |Ez|^2 is a field
  component magnitude, **not** the full electromagnetic energy density.

All arrays, exact chosen parameters, and measured numerical residuals are
written to `data/fiber_wave_*.npz` and `data/fiber_wave_metrics.json`. The
figures contain synthetic-model labels and physical units. Re-run with:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m textile_sim.fiber_wave
python -m unittest discover -s tests -p 'test_fiber_wave.py' -v
```

## Validation scope

The 17 unit tests check index matching, passive absorption, lossless optical
theorem, angular integration, the two independent Rayleigh asymptotes, retained
coefficient boundary residuals, actual boundary fields against the
untruncated incident wave, multipole convergence, illumination-angle
covariance, incoherent averaging, single-cylinder cluster reduction, local
versus global flux, translation/rotation covariance, scalar reciprocity, field
reconstruction, direct cluster interface traces/weighted normal derivatives,
the large-separation limit, and invalid geometry rejection. Some tests contain
multiple physical cases; the suite has 17 named test methods.

This establishes a reproducible and checked solver for the stated canonical
Maxwell problems. It does not validate the geometry or indices of real fabric,
the fidelity of a complete garment image, or a claimed metasurface advantage.
Fullwave agreement at this level and plausible high-level cloth images are
distinct claims.

## Additional optical-size matched wave/ray benchmark

The implementation was subsequently extended to the exact same seven-fiber
geometry used by `ply_ray.py`: radius 5 um, inter-fiber gap 0.4 um, synthetic
index 1.55. This prevents a submicron-only wave calculation from being
presented as if it directly checked an optical-size yarn ray model.

At 550 nm, the regular bundle gives Csca = **56.30824 um (Ez)** and
**56.57241 um (Hz)**. For Ez, N=83 versus N=91 changed the differential
intensity by **9.7794e-10 relative L2**. Replacing repeated translation-block
Hankel evaluations by a lookup of the unique orders gave identical numerical
output; an isolated observed solve changed from **9.886 s to 0.488 s** on the
current execution environment. These are observed timings, not hardware-
independent performance promises.

The full matched ensemble uses 450/550/650 nm, the regular geometry plus two
center-jitter realizations (sigma = 0.06 um), and both polarizations. Each of
the 18 wave configurations has N versus N+8 convergence checks. Nine required
an additional increment of eight; the accepted maximum change was
**9.1889e-8**, below the declared **1e-7** gate. The largest global-versus-local
energy-flux residual was **9.9454e-15**. The paired ray experiment used 150,000
rays per geometry and polarization, 900,000 total. The recorded total benchmark
time was **67.72 s**.

The resulting agreement must not be overstated. After equal two-degree binning
and removal of the central +/-6 degrees from the error metric, the absolute
differential-pattern relative L2 errors are still **0.5064 (Ez)** and
**0.5465 (Hz)**. The ensemble backward cross-sections are:

| Polarization | Exact wave, um | Power rays, um | Ray Monte Carlo SE, um | Relative difference |
|---|---:|---:|---:|---:|
| Ez | 7.3946 | 6.8365 | 0.0180 | -7.55% |
| Hz | 5.3872 | 4.0948 | 0.0148 | -23.99% |

The small wavelength/geometry ensemble smooths the exact wave fringes, but does
not establish the ray-wave mean agreement reported for a different geometry
and illumination in the 2025 cloth work. This is an actual negative/qualifying
simulation result. It identifies a model-bridging task still to solve; it is
not an instruction to rescale the wave or ray curves. Forward-cone sensitivity
is also recorded, so the selected exclusion is not the only reported statistic.

Artifacts: `data/fiber_wave_textile_matched.npz`,
`data/fiber_wave_textile_matched_metrics.json`, and
`data/fiber_wave_textile_matched.png`. Run:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m textile_sim.fiber_wave --textile-benchmark
```

The separate independent review of the power tracer and its wave interface is
in `notes/review_fiber_vs_ray.md`. Another implementer independently reviewed
the wave module using Graf translation, volume absorption integration,
reciprocity, and scale invariance; see `notes/review_wave_module.md`.
