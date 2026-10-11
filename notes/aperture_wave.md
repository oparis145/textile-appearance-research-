# Aperture-wave module: model, executable experiments and verification

## Physical scope

This module propagates a scalar field through a finite thin transmission mask in
the Fraunhofer/paraxial limit. It addresses direct light through textile pores.
It does not calculate reflection, absorption or scattering in yarn material, nor
inter-fiber electromagnetic coupling. It supplies a diagnostic angular kernel;
it is not silently injected into the ray-rendered cloth BSDF.

For each mutually coherent illumination component, the input is a complex mask
`a(x,y)` and optional incident field `u(x,y)`. The default is a normally incident
plane wave. A Gaussian example uses amplitude

\[
u(x,y)=\exp[-((x-h)^2+y^2)/w_0^2],
\]

so its intensity is `exp(-2r²/w0²)`. Independent source directions, wavelengths,
or random instances are combined only after taking the squared field magnitude.

## Exact discrete normalization

Let `M` be the number of original mask pixels, `N` the number after zero padding,
and `U_k = DFT[a u]_k` using NumPy's unnormalized forward FFT. Returned bin powers
are

\[
P_k=\frac{|U_k|^2}{N\sum_m|u_m|^2}.
\]

Discrete Parseval gives

\[
\sum_kP_k=\frac{\sum_m|a_mu_m|^2}{\sum_m|u_m|^2}=T_\mathrm{direct}.
\]

The denominator is `N M` under unit plane illumination. Padding refines angular
sampling without creating incident light. A binary open-pore mask has
`T_direct = open area / illuminated area`. Fractional area coverage is not the
same thing as field amplitude: passing a fractional open-area map directly as
`a` would yield `mean(a²)`. Use a resolved binary visibility mask or explicitly
derive an appropriate subpixel field model.

The angular grid uses direction-cosine coordinates `q_x = λ f_x`, `q_y = λ f_y`;
near the axis these equal radians. The density is `P/(dq_x dq_y)`, approximately
power fraction per steradian. Results flag power outside the propagating cone
and outside a5° paraxial cone; those diagnostics do not make large-angle scalar
results accurate. Finite-pixel FFT aliasing is a separate approximation from
angular padding. Parseval is numerical consistency, not validation of Maxwell
boundary conditions or a measured fabric.

## Incoherence, spectra and detector

For normalized incident spectral/source weights `w_j`, the instrument result is

\[
P_\mathrm{det}=\mathcal A_\mathrm{NA}
\left[\sum_jw_j\,\mathcal R_j(P_j) * S * H\right].
\]

`R_j` conservatively remaps intensity-bin mass to a common angular grid; `S` is a
Gaussian angular source distribution and `H` optional Gaussian detector blur.
Their variances add in the small-angle shift approximation. The source width is
the standard deviation **per angular axis**, not a FWHM or a rectangular-light
half width. Zero continuation avoids circular convolution wrapping. Boundary
escape and rejected NA power remain explicit; no renormalization hides them.
Three equal-power bands are not a calibrated RGB colorimetric model.

`angular_mass_within` integrates a circular acceptance with partial-bin boundary
area quadrature. This removes most staircase error from accepting bins solely by
their center; residual spatial/bin approximation is included in convergence runs.

## API and reproduction

```python
from textile_sim.aperture_wave import (
    fraunhofer, blur_incoherent, incoherent_average,
    woven_gap_mask, angular_mass_within)

mask = woven_gap_mask((512, 512), pixel_um=1, pitch_um=128, gap_um=30)
bands = [fraunhofer(mask, 1, wavelength_um=w, pad_factor=2)
         for w in (.45, .55, .65)]
result = blur_incoherent(incoherent_average(bands), source_sigma_deg=1)
assert result.total_power <= mask.mean() + 1e-12
```

```bash
python -m unittest discover -s tests -p test_aperture_wave.py -v
python -m textile_sim.aperture_wave --output data
```

The actual suite has15 passing tests: arbitrary complex-mask Parseval; open and
closed limits; analytic slit first zero; continuum-sinc pixel refinement;
common-angle invariance under padding; opposite-phase incoherent noncancellation;
spectral power conservation; Gaussian angular variance addition; explicit window
and NA losses; passive direct transmission; repeatable disorder; circular
acceptance area; Gaussian-aperture erf; incident-power scale invariance; and
invalid parameters. Last dedicated run:0.278s on this environment.

## Executed synthetic sweeps

All period sweeps use a finite512×512um patch,1um pixels and128um yarn pitch.
Gap widths are exactly10,30 and80um on this grid. The three VIS bands450,550 and
650nm carry equal incident power. The following percentages are conditional on
the already-transmitted direct-pore power; they are not whole-cloth transmittance.

| Gap | Geometric direct transmittance | Power within0.5° radius, point source | Same, source sigma1° |
|---|---:|---:|---:|
|10um|0.61035%|8.039%|4.585%|
|30um|5.49316%|50.016%|8.922%|
|80um|39.0625%|84.473%|10.642%|

The coherent fine grating structure is strongly smoothed under an extended
source, while the transmitted-power budget remains controlled. Wider gaps place
more of their direct power close to the original direction. These are computed
consequences of the declared masks/source model, not material identification.
The periodic-versus-jittered example also changes pore areas; its raw intensities
must not be interpreted as a pure coherence ablation at identical transmittance.

For an isolated slit, the first zero follows `q≈λ/w`; the550nm predictions are
about3.151°,1.050°,0.394° for10,30,80um widths. The test checks a slit whose first
zero lies exactly on an FFT bin against its analytic null, independently of the
periodic-array pattern. For a30um square pore illuminated with a10um-waist
Gaussian beam, computed direct power fractions are0.99463,0.72388,0.08045 for beam
offsets0,12,22um. Partial overlap loses power before it broadens the angular field.

## Numerical convergence and corrections made

A40um pore in a128um window gives the following power inside a0.5° disk:

| Refinement | Values |
|---|---|
|Physical pixel2→1→0.5um, padding4|0.06603478→0.06597219→0.06595656|
|Padding2→4→8→16, pixel1um|0.06556620→0.06597219→0.06611305→0.06613712|

Pixel refinement1→0.5um changes this quantity by about0.024%; padding8→16 by
about0.036%. These checks apply to the representative smooth integrated metric,
not every high-frequency diffraction pixel. The largest plane-wave sweep
Parseval residual is about1.11e-16 of incident power. The Gaussian-beam sweep
residual reaches3.33e-16. Neither residual measures physical-model error.

Review found and corrected an integer-pitch casting failure, an ambiguous
coarse-grid gap width, and circle-boundary integration oscillations. The final
sweeps use a physically consistent1um gap raster, conserved spectral remapping,
partial-boundary integration, and explicit lost-power accounting.

## Saved outputs

- `data/aperture_gap_source_sweep.png`: gap/source-size matrix.
- `data/aperture_periodic_vs_jitter.png`: finite ordered/disordered masks.
- `data/aperture_slit_wavelength.png`: analytic-width/wavelength comparison.
- `data/aperture_gaussian_beam.png`: coherent local-beam truncation experiment.
- `data/aperture_metrics.json`: raw computed scalar results and convergence.
- `data/aperture_arrays.npz`: masks and angular marginals.
- `data/aperture_tests.log`: executed unittest output.

The method relationship and primary-source audit are in
`notes/ray_wave_literature.md`.
