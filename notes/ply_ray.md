# Module: dielectric-fiber / ply power rays

This is an independent, executable research prototype. It is **not** a reproduction
of Yu, Walter, Marschner and Weidlich's 2025 ray–wave cloth paper: that paper's
Gaussian beam, three-dimensional twisted ply, wave-calibrated fluctuations and
cloth shading construction are different. Here the controllable baseline is a
two-dimensional cross section of a finite cluster of circular, infinite,
isotropic, smooth fibers. It resolves inter-fiber occlusion, refraction and
multiple encounters rather than adding isolated-fiber intensities.

## Coordinates, quantities and assumptions

- Fibers have axes parallel to z. Centers, radii, ray positions and path lengths
  use micrometres. The ray plane is x–y.
- The default incident beam propagates along +x. The exit angle is
  `atan2(d_y,d_x)` in radians, measured from +x; the hemisphere classification is
  relative to the incident direction if `incident_angle_rad` is changed.
- `Ez` means s-polarized electric field parallel to the fiber axis. `Hz` means
  p-polarized electric field in the ray plane. TE/TM labels are intentionally not
  used because their convention changes between communities.
- The unpolarized calculation draws an equal-probability mixture of Ez and Hz
  incident rays. Each ray **retains its polarization channel** at every boundary;
  repeatedly replacing it by the averaged Fresnel coefficient would incorrectly
  erase the polarization state selected by previous interfaces.
- Reference `n_fiber=1.55`, `n_host=1.0`, radius 5 um and gap 0.4 um are declared
  synthetic parameters, not optical measurements of silk, cotton or any named
  textile. No wavelength is implied by a wavelength-independent real index.
- A scalar or per-fiber Beer attenuation coefficient can be fixed as an input.
  The real-index Fresnel plus Beer approximation does not model the surface
  optics of strongly absorbing complex-index media. There is no dyeing, fading,
  molecular absorption inversion, birefringence or material classification.
- Fibers must be strictly disjoint, with positive gaps. Contact singularities,
  overlapping media, non-circular sections, rough interfaces and helical axes
  are not supported by this two-dimensional module.

## Forward mathematics

For a unit direction d, origin o, circle center c and radius a, let q=o-c.
Intersection parameters solve

\[
 t^2+2(q\cdot d)t+q\cdot q-a^2=0.
\]

The nearest positive root above a stated numerical self-intersection tolerance
is taken among all circles for an external ray. For an internal ray the far root
of its current circle gives the next exit surface. At exact surface positions
the next ray is not displaced: positive-root rejection prevents a false
self-intersection without deleting path length from the Beer integral.

Let n be the interface normal pointing into the incident medium, so
\(c_i=-d\cdot n\geq 0\), and let \(\eta=n_i/n_t\). Then

\[
 c_t=\sqrt{1-\eta^2(1-c_i^2)},\qquad
 d_r=d+2c_i n,\qquad
 d_t=\eta d+(\eta c_i-c_t)n.
\]

A negative radicand means total internal reflection. The power coefficients are

\[
 R_s=\left(\frac{n_i c_i-n_t c_t}{n_i c_i+n_t c_t}\right)^2,\qquad
 R_p=\left(\frac{n_t c_i-n_i c_t}{n_t c_i+n_i c_t}\right)^2.
\]

At every interface a ray chooses reflection with probability R and transmission
with probability 1-R. Its weight is unchanged by this Monte Carlo choice, so
ensemble power is correct. No extra eta-squared radiance factor is multiplied:
these rays carry power, not a radiance density under a solid-angle change.

An internal chord of length L changes a weight w to
\(w'=w\exp(-\mu_a L)\), depositing \(w-w'\) into absorbed power. There is
no stochastic termination for weak weights, so absorption and the residual
accounting are transparent.

The per-ray incident-power identity is

\[
 1=w_{\rm back}+w_{\rm encountered,forward}
   +w_{\rm uncollided,forward}+w_{\rm absorbed}+w_{\rm residual}.
\]

The last term is the remaining weight of a ray that reaches the maximum number
of interfaces, or a documented numerical intersection failure. It is never
forced into transmission or used to renormalize the other channels. A final
intersection query recognizes rays escaping immediately after the last allowed
interface. The `max_events` limit therefore counts actual interfaces.

## Independent analytical reference for a single cylinder

The Monte Carlo tracer is checked against a second implementation that does not
use vector intersections. For a normalized signed impact parameter b/a, define
\(i=\arcsin(b/a)\), \(r=\arcsin(n_h\sin i/n_f)\), and one internal chord
\(L=2a\cos r\). External reflection has
\(\theta_0=\pi-2i\) and weight R. A transmitted path with p internal chords
and p-1 internal reflections has

\[
 \theta_p=(p-1)\pi-2i+2pr,\qquad
 W_p=(1-R)^2 R^{p-1}\exp(-\mu_a pL),\quad p\geq1.
\]

Angles are wrapped into [-pi,pi). The power coefficient on the internal exit
interface equals that on the corresponding external entry interface by Fresnel
reciprocity. Midpoint integration over impact parameter sums these exit orders.
The unresolved internal power after the final order is explicitly reported.
This checks complete angular transport, not just the sum of weights.

For an index-matched absorbing circle, there is also an independent chord
integral:

\[
 T=\frac{1}{2a}\int_{-a}^{a}
 \exp[-2\mu_a\sqrt{a^2-b^2}]\,db.
\]

Each recorded ray path and transmitted weight is compared to that chord formula.

## Beam and cross-section normalization

A uniform beam samples transverse impact parameter in
\([b_0-W/2,b_0+W/2]\). Each input ray represents 1/N of beam power. The default
W is the cluster's projected bounding width, so different bundle sizes have
different total incident powers when the irradiance per unit width is fixed.
Reported fractions always divide by that run's input beam power.

For an angular bin of width delta theta, the estimate is

\[
 p_j=\frac{1}{N\Delta\theta_j}\sum_i w_i\,
 1\{\theta_i\in j,\;i\text{ escapes}\}.
\]

Its angular integral is the escaping power. `intercepted_ray_dcs_um_per_rad`
multiplies the encountered-ray part by W. The integrated unit is um: this is a
cross section per unit z length for **geometrically intercepted rays**.

It is **not the Maxwell scattered-field cross section**. A wave calculation
subtracts the incident field coherently; forward diffraction and extinction
interference then matter. For example, an optically large lossless cylinder can
have scattering/extinction near twice its projected geometric width, while the
ray-intercepted outgoing total equals its geometric width. For an index-matched
circle, geometrically encountered rays remain a forward delta although the
Maxwell scattering is zero. Comparisons to an exact-cylinder module must either
exclude a declared forward cone and compare absolute angular densities, or
construct a detector field model that treats the incident wave consistently.

A Gaussian beam is sampled without truncation from the normalized irradiance
profile exp[-(b-b0)^2/(2 sigma^2)]/(sqrt(2 pi) sigma). Its sigma is mandatory and
its result is a beam-specific response, not a plane-wave cross section. A
Gaussian irradiance in this ray module does not supply a Gaussian beam's phase
or its diffraction-limited waist divergence.

## Statistical uncertainty and reproducibility

For each output energy channel, the ordinary IID sample standard error is
`std(per_ray_channel, ddof=1)/sqrt(N)`. Histogram uncertainty uses the sum of
weights squared within each bin and includes the zero contribution of all
other incident rays. Error bars describe Monte Carlo sampling uncertainty,
not uncertainty in material parameters or model inadequacy. Channel estimates
are correlated; no independent-error addition is used for conservation.

The RNG seed and batch size are both recorded. Changing batch size changes the
order of RNG draws and therefore the individual Monte Carlo realization;
distributions should agree within sampling error, not bit for bit.

Run from the `textile_lab` directory:

```sh
python -m unittest discover -s tests -p test_ply_ray.py -v
python -m textile_sim.ply_ray --output-dir data
```

The reference suite contains 1/7/19-fiber clusters for Ez, Hz and unpolarized
light at 100,000 rays per condition; two fixed absorption levels; a more open
seven-fiber cluster; a full angular comparison against independent analytical
ray orders at 200,000 rays; and 32-seed Monte Carlo convergence at 2,000,
10,000 and 50,000 rays. Outputs are `ply_ray_summary.json`,
`ply_ray_angular.csv`, and three `ply_ray_single_quadrature_*.npz` files.

### Executed reference results

For lossless n=1.55, radius 5 um and gap 0.4 um, unpolarized backward beam-power
fractions were 0.08590, 0.19490 and 0.27929 for 1, 7 and 19 fibers. The respective
forward fractions were 0.91410, 0.80510 and 0.72071. These are geometric bundle
responses under their own projected-width beams, not observations of named
real textiles. The dense bundles have no unobstructed +x rays despite having
positive spaces between fibers. Increasing the seven-fiber gap to 3 um creates
0.07841 uncollided beam-power fraction.

The nineteen-fiber lossless run has mean internal path 36.947 um and mean
7.881 interface encounters. Its maximum was 52 encounters, below the 200 limit.
No numerical failures or residual power were observed in the reference
conditions. With fixed mu=0.02/um, its absorbed fraction is 0.497221; backward
and encountered-forward fractions are 0.150577 and 0.352202. The same geometry
and indices remain explicit inputs, with no dye or process model.

The full single-cylinder angular comparison at 200,000 rays gives maximum CDF
differences 0.001314 (Ez), 0.001934 (Hz) and 0.002389 (unpolarized) against
analytic ray-order quadrature. Refining the deterministic impact quadrature
from 32,768 to 131,072 points changes the reference CDF by about 2.1e-5.

Across 32 random seeds the observed standard deviations in backward power
are 0.008973, 0.003716 and 0.001701 for 2,000, 10,000 and 50,000 incident rays.
Corresponding mean predicted standard errors are 0.008806, 0.003956 and
0.001769. All three observed scatter estimates lie within the 95% range
expected for 32 Gaussian-approximation samples with those standard errors.
The initial eight-seed estimate at 10,000 rays happened to be unusually small;
it was retained while extending every budget to 32 seeds. No seeds were
discarded to make the convergence curve look cleaner.

The figure `data/ply_ray_overview.png` (also SVG) is generated directly from
these records and has been inspected for labels, axes and layout. The full
reference run represents 3,784,000 incident rays across its declared conditions
and convergence runs, plus deterministic ray-order quadrature.

## API example

```python
from textile_sim.ply_ray import hex_bundle, trace_bundle

centers, radii = hex_bundle(shells=2, radius_um=5, gap_um=0.4)
result = trace_bundle(centers, radii, n_fiber=1.55,
                      n_rays=100000, seed=20261010,
                      polarization="unpolarized", record_paths=40)
print(result["energy"])
theta = result["theta_rad"]
power = result["angular_power_per_rad"]["encountered_escaped"]
```

Use `return_rays=True` to inspect individual ray weights, internal lengths,
polarization codes, reflection/refraction counts and escape masks. The compact
`summary` dictionary is JSON serializable for ordinary multi-ray runs.

## Relation to the high-level fabric model

This module can test how spacing, packing, incidence direction and fixed fiber
optics change effective two-dimensional angular transport. It must not be
promoted to a three-dimensional cloth BSDF merely by revolving its histogram:
that would lose axial transport, solid-angle normalization and the three-
dimensional reciprocity constraint. A separate three-dimensional ray/path
tracer should use actual yarn/fiber geometry and a valid 3D fiber BSDF.

The simulated values are numerical/physical checks on a specified synthetic
geometry. They do not validate the appearance of a measured physical textile,
nor do they establish the benefit of a metasurface measurement.

## Primary methodological reference

Matt Pharr, Wenzel Jakob and Greg Humphreys, *Physically Based Rendering:
From Theory to Implementation*, fourth edition, section 9.3, gives the Fresnel,
Snell and power-versus-field conventions checked here:
https://pbr-book.org/4ed/Reflection_Models/Specular_Reflection_and_Transmission

The current code and the single-cylinder ray-order checker are independent
implementations. No external implementation is copied. The precise full-wave
and empirical cloth questions remain separate modules.
