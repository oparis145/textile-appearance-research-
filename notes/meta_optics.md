# Scalar external meta-optics measurement emulator

## What was actually implemented

`textile_sim/meta_optics.py` computes prescribed phase pupils, scalar propagation, sensor point-spread functions (PSFs), and a passive measurement matrix. It is a numerical instrument-design prototype. It does not simulate nanoposts, resonances, a fabrication process, vector polarization conversion, or a measured metasurface efficiency. The source is independent code written for this project.

The experiment asks a restricted, useful question: **does a pupil that makes four spots produce four independent combinations of angular and spectral incident power?** The answer depends on its design. In the executed nine-state experiment, a symmetric four-spot pupil has matrix rank 2, whereas one asymmetric four-spot pupil has rank 4 with the same aperture, four sensor regions, and assumed loss. Neither uniquely recovers nine arbitrary input weights.

This module is currently an independent forward operator. It has not been calibrated to a textile or jointly optimized with the fabric-rendering/inference modules. It supplies a way to replace an ideal channel-selection matrix with a physically propagated, nonnegative sensor response in later experiments.

## 1. Optical configuration and normalization

All lengths are in micrometres. The default circular pupil has radius `R=25`, design focal length `f=250`, and design wavelength `lambda0=0.55`. Thus the nominal aperture ratio is `R/f=0.1`. The pupil is sampled on a 512 by 512 grid with 0.5 µm pitch, then padded by two before propagation. The resulting computational sensor window is 512 by 512 µm with unchanged 0.5 µm pitch.

For target positions `t_c=(x_c,y_c)` in the nominal focal plane and nonnegative weights summing to one, the desired sum and phase-only projection are

\[
g(\mathbf r)=\sum_c\sqrt{w_c}\exp\!\left[i\left(-\frac{k_0|\mathbf r|^2}{2f}+\frac{k_0\mathbf r\cdot\mathbf t_c}{f}\right)\right],
\qquad \phi(\mathbf r)=\arg g(\mathbf r),\quad k_0=2\pi/\lambda_0.
\]

The transmitted field on a sampled clear-pupil mask `A` is

\[
u_0(\mathbf r)=\sqrt{\frac{\eta}{\sum A\,\Delta x^2}}\,A(\mathbf r)\,e^{i\phi(\mathbf r)}.
\]

Incident scalar power on the clear pupil is defined as one. Therefore

\[
\sum |u_0|^2\Delta x^2=\eta.
\]

`eta=0.8` is an explicitly assumed throughput penalty, not an estimate from a fabricated device or a value fitted from literature. The rejected fraction `1-eta` is outside this modeled field. Multiplexing and phase quantization subsequently redistribute the remaining power; they do not create additional power.

The complex sum is projected onto a phase-only pupil. Its target weights are not guaranteed realized power fractions, because the amplitude of `g` is discarded. Unwanted diffraction orders consequently appear in the computed PSF. At isolated sampled zeros of `g`, the code chooses phase zero; these are part of the finite raster approximation.

The same prescribed phase is used at every wavelength. This resembles an ideal geometric-phase target, but no polarization conversion model is included. In a physical Pancharatnam–Berry device, the converted polarization channel, conversion efficiency, leakage, and wavelength response must be separately modeled or measured. This assumption must not be interpreted as a broadband achromatic metalens.

For comparison, the single-focus baseline uses only the quadratic phase at the same design wavelength. It therefore follows the same fixed-phase law and is a diffractive phase-lens baseline, not an achromatic refractive lens. A future comparison with a conventional camera must include that camera's actual chromatic response, pupil, sensor sampling, spectral filters, and photon budget.

## 2. Propagation and physically labeled sensor coordinates

Incident direction `(theta_x,theta_y)` multiplies the pupil by

\[
u_\theta(x,y)=u_0(x,y)\exp\!\left[\frac{2\pi i}{\lambda}(x\sin\theta_x+y\sin\theta_y)\right].
\]

The Fresnel transfer-function propagator is

\[
u_z=\mathcal F^{-1}\left\{\mathcal F[u_\theta]\exp[-i\pi\lambda z(f_x^2+f_y^2)]\right\}.
\]

The global carrier phase is omitted. Input and output spatial pitch are identical in this formulation. The numerical Fourier frequencies are `fftfreq(N, dx)`; no focal-plane FFT coordinate is incorrectly substituted for a spatial output coordinate. Symmetric zero padding aligns physical origins, including odd input dimensions padded to even dimensions. A specific odd-grid origin regression test was added after review.

The transfer function has unit magnitude. NumPy's forward/inverse FFT pair therefore satisfies

\[
\sum_{ij}|u_z[i,j]|^2\Delta x^2=\sum_{ij}|u_\theta[i,j]|^2\Delta x^2=\eta
\]

up to roundoff. The FFT window is periodic: this equality alone does not establish accurate local intensity. Explicit padding and physical-pixel convergence are therefore measured below.

An optional scalar angular-spectrum comparison replaces the Fresnel transfer function by

\[
T_{\mathrm{AS}}=\exp\!\left[ikz\left(\sqrt{1-\lambda^2(f_x^2+f_y^2)}-1\right)\right]
\]

on propagating frequencies and suppresses evanescent frequencies. Any resulting loss of scalar field norm is reported. This is a scalar nonparaxial phase comparison, not a vector Maxwell/Poynting-flux validation. It is also not an implementation of the published band-limited angular-spectrum algorithm.

For a single off-axis carrier, fixed sensor distance `z=f` gives approximately

\[
\mathbf x_{\mathrm{spot}}\simeq \frac{\lambda}{\lambda_0}\mathbf t+f(\sin\theta_x,\sin\theta_y).
\]

The wavelength-independent focusing phase also has effective focal distance `f lambda0/lambda`, so wavelengths away from the design wavelength are defocused at the fixed sensor plane. The simulation therefore includes both spot displacement and defocus. Changing incidence and changing wavelength can resemble one another; four replicated spots do not automatically separate four wavelength bands.

## 3. Passive measurement matrix

Each simulated input state is a unit-power monochromatic plane wave entering the clear pupil. The nine hypotheses are the Cartesian product of wavelengths 450/550/650 nm and incidence angles `theta_x=-1/0/+1 deg`, with `theta_y=0`.

For four disjoint circular sensor regions `Omega_i`, the measured matrix is

\[
H_{iq}=\sum_{(m,n)\in\Omega_i}|u_z^{(q)}[m,n]|^2\Delta x^2.
\]

Therefore `H>=0` and each column sum is at most `eta`. For mutually incoherent input components of powers `s_q>=0`, measured optical power is `y=Hs`. Intensities add; fields from independent wavelengths or mutually incoherent angular source elements must not be summed before squaring. Coherent angular illumination would require the mutual coherence or complex amplitudes and is outside this linear-intensity model.

`H` maps optical power to optical power. It does not itself encode photon conversion, exposure, quantum efficiency, read noise, gain, or saturation. Photon-count predictions must add the wavelength-dependent factor `lambda/(h c)` and sensor quantum efficiency consistently. The current module also does not model a spatially extended image: an external field stop, relay mapping, magnification, etendue, and pupil variation over the field remain to be designed before connecting many textile patches to one sensor.

The reported `outside_roi_power = total_power - captured_power` includes desired-spot Airy tails, defocus, interference structure, and unwanted orders across the modeled sensor window. It is not a pure measurement of ghost-order power. Absorption/rejected-polarization loss `1-eta` is reported conceptually separately. No renormalization makes the four outputs sum to one.

### Executed symmetry ablation

All four sensor circles have radius 4 µm and are disjoint. Symmetric target positions are `(-10,-10), (10,-10), (-10,10), (10,10)` µm. The one asymmetric design uses `(-12,-9), (9,-12), (-7,11), (13,8)` µm. Both use the same aperture, phase-projection rule, eta, physical sampling, and total four-ROI area. The asymmetric design is a single prescribed comparison, not the result of an optimization or a design search.

| Computed quantity | Symmetric four spots | One asymmetric four-spot design |
| --- | ---: | ---: |
| Singular value 1 | 0.358443 | 0.404296 |
| Singular value 2 | 0.108654 | 0.119777 |
| Singular value 3 | 2.04e-17 | 0.057460 |
| Singular value 4 | 1.73e-17 | 0.023491 |
| Numerical rank, relative threshold 1e-8 | 2 | 4 |
| Nullspace dimension for nine arbitrary weights | 7 | 5 |
| Captured power at 550 nm, normal incidence | 0.447869 | 0.508588 |
| Outside-ROI power in that condition | 0.352131 | 0.291412 |

The asymmetric matrix's condition number over its four nonzero singular values is 17.21. The symmetric matrix has duplicate upper/lower responses because all input tilts are in x and the pupil and ROIs are symmetric in y. Removing this symmetry adds independent combinations without adding sensor regions. This is a computed observation for this input-state family and these pupils, not a universal advantage of asymmetry.

The rank result concerns recovery of arbitrary mixtures of the nine states. Rank alone is not a complete assessment of classification among nine isolated hypotheses or estimation of two known low-dimensional parameters. Those tasks depend on the relevant columns, illumination/intensity nuisance variables, noise, and parameter sensitivities. For the symmetric design, the normalized column similarity of `450 nm/-1 deg` and `650 nm/+1 deg` is 0.999568, demonstrating one especially strong angle–wavelength ambiguity when input intensity is unknown. The three normal-incidence columns are exactly proportional in this symmetric example.

Increasing rank from two to four does not establish a practical textile-measurement gain. Such a gain should be tested by composing `H` with a calibrated textile forward model, adding realistic noise/loss, and comparing prediction of held-out lighting/viewing conditions against a strong RGB baseline. An optimization could act on the singular values of a task-specific Jacobian after photon-noise weighting, rather than maximizing the visible number of spots. No such optimization or experimental validation is claimed here.

### Captured power across all tested input states

| Wavelength | Incidence x | Symmetric | Asymmetric |
| --- | ---: | ---: | ---: |
| 450 nm | -1 deg | 0.154351 | 0.173536 |
| 450 nm | 0 deg | 0.297789 | 0.329599 |
| 450 nm | +1 deg | 0.154351 | 0.177255 |
| 550 nm | -1 deg | 0.150455 | 0.178322 |
| 550 nm | 0 deg | 0.447869 | 0.508588 |
| 550 nm | +1 deg | 0.150455 | 0.177476 |
| 650 nm | -1 deg | 0.150247 | 0.182662 |
| 650 nm | 0 deg | 0.294262 | 0.320697 |
| 650 nm | +1 deg | 0.150247 | 0.157508 |

These are fractions of incident power on the clear pupil. All propagate total scalar power 0.8, with the rest outside the four ROIs. No incident powers were increased for the multiplexed design.

## 4. Phase quantization and baseline

Nearest-level phase quantization uses `phi_L = (2 pi/L) round[L phi/(2 pi)]`, with wrapped phase error bounded by `pi/L`. The field amplitude remains unchanged. Quantization therefore moves power between sensor regions and outside them rather than implementing an additional arbitrary absorption factor.

| Design at 550 nm, normal incidence | ROI count | Captured incident-power fraction |
| --- | ---: | ---: |
| Single quadratic phase lens | 1 | 0.675569 |
| Symmetric four-focus continuous phase | 4 | 0.447869 |
| Four-focus, 2 phase levels | 4 | 0.173346 |
| Four-focus, 4 phase levels | 4 | 0.364934 |
| Four-focus, 8 phase levels | 4 | 0.425903 |
| Four-focus, 16 phase levels | 4 | 0.442275 |

The single-focus and four-focus baselines use different total ROI areas. This table measures how their energy is distributed; it is not an equal-detector-area performance comparison. The symmetry ablation above does use equal total ROI area.

## 5. Numerical validation and limits

**Eleven tests pass** in `data/meta_tests.log`: unit pupil power for eta=0/0.4/1; Parseval under padding and tilt; zero-distance identity; physical-origin preservation for odd-grid padding; bounded quantization error and power; analytic Airy profile; Airy encircled power; incident-angle focal translation; off-axis carrier wavelength translation; positive disjoint-ROI power budget; optional angular-spectrum passivity; and invalid-input handling. Some tests cover more than one property.

The analytic circular-pupil benchmark uses the normalized intensity

\[
I(r)/I(0)=[2J_1(v)/v]^2,\qquad v=2\pi Rr/(\lambda f).
\]

At 0.25 µm physical pitch, the maximum normalized intensity discrepancy over `|x|<7 um` is 0.004307. The computed first Airy disk (radius 3.354092 µm) contains 0.837785 of unit transmitted power, consistent with the analytic approximately 0.8378 result. Exact scalar roundoff conservation is not used as a substitute for this spatial benchmark.

| Convergence comparison | Captured four-ROI power |
| --- | ---: |
| 128 µm initial window, dx=0.5 µm, padding 1 | 0.448781 |
| Same, padding 2 | 0.447882 |
| Same, padding 4 | 0.447869 |
| Same physical window, dx=0.25 µm, padding 4 | 0.445549 |
| Default physical grid/window, scalar angular spectrum | 0.447505 |

Padding 2 to 4 changes the selected detector quantity by about 0.003%. Halving the physical pixel size changes it by about 0.52%; the finite-pixel pupil and circle-boundary rasterization retain that residual. The scalar angular-spectrum comparison differs from default Fresnel by about 0.081% at the design wavelength and normal incidence. Maximum relative Fresnel energy residual over the principal nine-state experiment is 4.16e-16. The convergence experiment assesses the symmetric design at the design condition; it is not a claim that every off-design ghost order or asymmetric singular value is converged to those same percentages.

There is an important paraxial limitation. The phase projection creates high diffraction orders: normal-incidence sampled pupil-spectrum power outside a 10-degree cone is 0.127/0.171/0.222 of incident power at 450/550/650 nm. The intended ROIs lie near the paraxial central region, where the above scalar comparison is reassuring. The model should not be used to make accurate claims about wide-angle ghost distribution, vector power flow, subwavelength phase edges, or fabricated efficiency. Increasing sampling/padding does not cure an inappropriate scalar or fixed-phase physical model.

Other unimplemented elements include unit-cell dispersion, Jones/Mueller response, polarization leakage, fabrication tolerance, the field dependence of a real lens/relay, calibrated broadband source spectra, actual sensor response, and measured textile data. A realizable metasurface design would replace the prescribed scalar pupil with its wavelength/angle/polarization-dependent complex transmission and then repeat this validation and the information comparison.

## 6. Reproduction and outputs

From the `textile_lab` directory:

```bash
python -m textile_sim.meta_optics
python -m unittest discover -s tests -p test_meta_optics.py -v
```

The experiment writes actual computed arrays to `data/meta_arrays.npz` and metrics to `data/meta_metrics.json`. The main function reproduces the five PNG figures and experiment metrics. `data/meta_validation_metrics.json` records the separately executed analytic Airy check. Test logs preserve the executed unittest results.

| File | Content |
| --- | --- |
| `meta_psf_wavelength_angle.png` | Nine symmetric four-spot PSFs, fixed physical coordinates/color scale and fixed detector ROIs |
| `meta_single_lens_baseline.png` | Nine single-lens PSFs under the same incident states and fixed-phase assumption |
| `meta_measurement_matrix.png` | Symmetric H and normalized column similarities |
| `meta_symmetry_ablation.png` | Equal-ROI-area symmetric/asymmetric H, singular values, captured power |
| `meta_lens_quantization.png` | Single and four-focus fields with 2/4/8/16 phase levels |

The figures were opened and visually checked. They are numerical plots of propagated fields, not image-generated illustrations.

## 7. Primary literature and relation to existing hardware

1. **Liu, Xu, and Guo, MetaSpectra+**, CVPR 2026 project: <https://meta-imaging.qiguo.org/>; paper: <https://arxiv.org/html/2603.09116v1>; public repository: <https://github.com/guo-research-group/MetaSpectra-plus>. The official project and paper were inspected, as were repository structure and README. The actual system uses two metasurface layers together with a refractive lens: beam splitting, channel-dependent dispersion, and focusing have distinct roles. Two achromatic and two orthogonally dispersed channels show why merely making four symmetric spots is not equivalent to a spectropolarimetric imager. Its first-layer random interleaving and physical wavelength response differ from our phase-of-a-sum pupil. Public reconstruction/training code was located; externally hosted PSF/model files and training were not downloaded/run. This project is **not** reproduced here.

2. **Arbabi et al., Dielectric metasurfaces for complete control of phase and polarization with subwavelength spatial resolution and high transmission**, Nature Nanotechnology 2015, DOI <https://doi.org/10.1038/nnano.2015.186>; primary institutional record: <https://authors.library.caltech.edu/records/kv58m-mcb25>. Its abstract/record establish a physical phase/polarization platform, but they do not provide a fabrication or efficiency model for the pupils in this notebook. No published efficiency is imported into eta=0.8.

3. **Matsushima and Shimobaba, Band-Limited Angular Spectrum Method for Numerical Simulation of Free-Space Propagation in Far and Near Fields**, Optics Express 2009, DOI <https://doi.org/10.1364/OE.17.019662>. This is a relevant primary numerical-propagation reference. Full-text access returned a rate limit/challenge during this work; the algorithm is not claimed to have been implemented. Our propagator is the explicitly written padded Fresnel transfer-function model, with a scalar angular-spectrum phase comparison and measured convergence.

The cloth paper by Yu et al., DOI 10.1145/3763359, models material scattering and transmission. This external pupil emulator acts after incident angular/spectral optical signals have been specified; it is a separate measurement-optics module. Its relation to textile appearance must be established through a calibrated forward chain, not inferred from the use of diffraction in both modules.
