# Final independent review: physical module connections and reporting scope

Review date: 2026-10-10. Reviewer: `aperture_wave_review`, independent of the root geometry/render/camera implementation. This review examined `run_fabric_experiments.py`, `textile_sim/render.py`, `textile_sim/camera.py`, their stable outputs and earlier module notes. The in-progress `fiber_wave_beam.py` and `validate_render.py` were not modified or reviewed as completed code. Some saved validation metrics were read as a snapshot; they must be replaced by the final validation run in the main report.

## 1. Disposition

No new numerical blocker was found in the executed default fabric/camera driver. In particular, the driver does **not** add aperture diffraction on top of ray transmission. It saves the geometry-derived diffraction calculation as a separate diagnostic. The review identified several interpretation/metadata issues; the root author added object-referred coordinate, post-collection photon-budget, output Nyquist, and pre-clipping variance descriptions to `camera.py`. Those changes were inspected. Updating the corresponding plot captions and saved camera metadata is part of the root's final integration.

The scientific scope remains **a checked set of connected and separately benchmarked optical modules**, not one fully coupled electromagnetic-to-garment simulator. Every major figure should say which model generated it.

## 2. Actual dataflow: connections that exist and do not exist

| Connection | Executed status | Meaning and remaining boundary |
| --- | --- | --- |
| Procedural 3D fiber geometry → Mitsuba renderer | Connected | The actual saved cubic B-spline fiber curves are intersected by the renderer. A pinned Chiang2016 fiber BCSDF supplies local ray-optical transport. |
| Mitsuba linear-radiance macro image → camera MTF/pixel/noise model | Connected | The camera applies an incoherent spatial transfer function, area averaging, Poisson/read noise, and display encoding to the saved rendered image. The input already has finite renderer sampling and Monte Carlo uncertainty. |
| Actual 3D geometry → Embree normal visibility → gap FFT | Connected, separate result | Rays classify open paths through the same rendered splines. That binary projection becomes a zero-thickness opaque aperture for a separate direct-pore diffraction experiment. It is not inserted into the rendered images. |
| Exact 2D Maxwell solver ↔ 2D ply power-ray tracer | Matched benchmark | The seven-cylinder optical-size benchmark compares the same stated radius, gap, refractive index, wavelength/geometry ensemble, and angular bins. It is a comparison, not a transfer of the exact wave field into the ray tracer. |
| 2D ply power-ray samples → positive circular mixture | Connected | An angular density is compressed and checked against separate random rays for the same geometry. It is not used as a three-dimensional BSDF in the fabric renderer. |
| Prescribed phase pupil → scalar propagation → sensor H | Connected within meta-optics module | A separate ideal measurement emulator computes PSFs and a passive 4×9 matrix. It is not calibrated to the textile angular distribution, camera RGB image, or a fabricated metasurface. |
| Exact 2D Maxwell solver → 3D fabric-rendering BSDF | **Not implemented** | The 3D fabric images are not wave-corrected or generated from the exact-cylinder coefficients. |
| Gap diffraction → camera/fabric image | **Not implemented** | The current image contact sheet and camera examples contain no field-level gap diffraction contribution. |
| Metasurface H → inverse textile parameters → held-out appearance | **Not implemented** | No end-to-end parameter estimation or measured-fabric appearance improvement is demonstrated. |

The 2D modules use infinite parallel cylinders and micrometres, whereas the 3D renderer uses helical B-splines in millimetres. A radius/gap match in one benchmark does not erase the axial/twist, polarization, phase, coherence, and solid-angle differences. A circular probability density in radians cannot be revolved into a reciprocal three-dimensional BSDF without an independently defined transport model.

The current matched wave/ray benchmark is particularly valuable because it does not automatically agree: the saved notes report approximately 0.506/0.547 relative L2 differences after the stated +/-6-degree forward exclusion, and different backward cross-sections for Ez and Hz. These are model-bridging discrepancies under the specified synthetic experiment. They should remain visible in the report instead of being hidden by normalized curves or a statement that ensemble averaging has already validated the 3D ray model.

## 3. What the fabric images demonstrate

The executed main images contain 740 explicit fibers per patch, radius 4 µm, yarn pitch 200 µm, and one synthetic isotropic optical parameter set. Plain, twill and satin use the same nominal fiber packing, index 1.55, absorption 2 mm^-1, local roughness, and display exposure. Their continuous cross-fiber clearance certificates passed. These are controlled weave comparisons, not fitted silk/cotton/linen or blend models. Satin is a weave label, not evidence that the sample is silk.

The renderer is `llvm_ad_rgb` with an intensity path integrator. It does not propagate complex electromagnetic phase or implement Yu et al.'s wave-calibrated random field. **Its residual random bright/dark grain is Monte Carlo estimator noise, not optical wave speckle.** Some stable fine structure also comes from actual resolved fiber geometry and geometric highlights. Neither should be labeled as measured fiber roughness, calibrated fuzz, or Maxwell interference. The separate Maxwell/aperture plots are the places where coherent wave interference was actually computed.

Main 256×256 images use 192 samples per pixel; the 512×512 macro uses 256 samples per pixel. These are finite numerical estimates. An independent seed/sample-convergence analysis can bound rendering uncertainty, but a single image is not a noise-free ground truth. Do not compare picture grain across modes as if it were solely a material property: path distributions and Monte Carlo variance differ.

The two reflection columns change the azimuth of the same finite area source at fixed view. They demonstrate a sampled directional-light response. They are not a dense BTF/BRDF capture and do not demonstrate prediction for an unseen view or unmeasured real cloth. The back-lit column uses a luminous opposite hemisphere, a different illumination condition from either reflection column.

The linear-image mean is outgoing radiance averaged over one orthographic image. **It is not hemispherically integrated reflectance or transmittance.** In particular, `plain_back_diffuse.mean_linear ≈ 0.709` does not by itself mean that 70.9% of all incident optical power transmits through the cloth. Likewise, the front/back image means cannot simply be added as R+T. Directly visible background through pores, angular scattering, source normalization, camera direction, and field weighting all enter the image mean.

Light `halfwidth_deg=7` describes a square emitter's geometric angular half width. It is not the Gaussian standard deviation used by `aperture_wave.blur_incoherent`. The main comparisons reuse the same emitter geometry/radiance; no exact equal-irradiance source-width sweep is established by these results.

The radius-normalized absorption mapping is explicitly pinned to Mitsuba3.9.1 and source-audited. This is necessary for internal physical units; it does not turn the synthetic index/absorption into measured optical constants of a named textile.

## 4. Camera comparison: what is normalized

The input macro spans 0.8 mm across 512 samples, giving **1.5625 µm per object-referred sample**. This value comes from the object-space field width divided by renderer resolution. It is not an actual detector pitch unless magnification is defined accordingly. A physical detector needs a magnification/relay map before object-space areas can be converted into sensor areas.

The model's detected-electron density is held fixed while changing NA. It therefore isolates the MTF/resolution effect at a **matched detected photon budget**. It does not automatically model the roughly NA² collection scaling that can occur at fixed object radiance, exposure, and other optical conditions. An equal-exposure physical camera sweep must explicitly model collection, throughput, magnification, spectrum, quantum efficiency, and saturation. Current figures should not claim that NA can be increased without a corresponding physical photon-budget change or that this is a calibrated camera exposure model.

The circular-pupil incoherent cutoff is `f_c = 2 NA/lambda`, at the assumed lambda=0.55 µm. The input Nyquist is 0.32 µm^-1, which exceeds all three tested cutoffs. The new output diagnostic distinguishes final sampling:

| NA | Binning | Object-referred output pitch, µm | Output Nyquist, µm^-1 | Optical cutoff, µm^-1 | Nyquist exceeds cutoff? |
| --- | ---: | ---: | ---: | ---: | --- |
| 0.02 | 1 | 1.5625 | 0.32 | 0.072727 | Yes |
| 0.04 | 1 | 1.5625 | 0.32 | 0.145455 | Yes |
| 0.08 | 1 | 1.5625 | 0.32 | 0.290909 | Yes |
| 0.04 | 2 | 3.125 | 0.16 | 0.145455 | Yes |
| 0.04 | 4 | 6.25 | 0.08 | 0.145455 | No |
| 0.04 | 8 | 12.5 | 0.04 | 0.145455 | No |

The bin4/bin8 cases intentionally demonstrate coarse sampling after pixel integration; a box aperture attenuates high frequencies but is not an ideal antialias low-pass. An input-grid Nyquist flag does not mean these final outputs are alias-free. Furthermore, the input is already a box-filtered finite render. Merely passing a Nyquist inequality does not prove absence of earlier aliasing or integration error.

`integrate_pixels` averages areas; expected electrons multiply that average by the output pixel area. Total expected photons for a uniform scene and fixed field remain consistent while counts per output pixel grow. Read noise is drawn once per resulting sample. This corresponds to a larger effective pixel or idealized pre-read aggregation, not arbitrary software binning of already read noisy pixels. Full-well capacity is fixed by the synthetic configuration rather than scaled automatically with binning.

`noiseless` means **before added detector noise**, not before renderer Monte Carlo noise, model error, blur, or aliasing. The stored `rmse_noise` compares each noisy detector result with its own blurred/binned reference. It measures the extra detector-noise term, not appearance accuracy relative to a real cloth or a converged rendering. Lower per-pixel noise after binning does not show that the lost fine texture is recovered.

`radiance_noise_variance` is the analytic pre-clipping Poisson-plus-read variance. At saturation, the code applies a post-read signal ceiling; the resulting clipped variance and mean differ. All main camera cases currently report zero saturation, so this caveat does not invalidate their reported detector-noise RMSE. Independent RGB read/shot noise in an otherwise neutral render can create colored grain; that is not a simulated dye spectrum or material-dependent color.

## 5. Direct-gap energy must not be counted twice

The binary visibility fraction is already an incident-power fraction for the projected thin opaque-mask model. The Fraunhofer FFT redistributes exactly that direct-pore power over angle. For an identically defined incident condition and angular measure, a hypothetical conservative replacement would be

\[
K_{\mathrm{hybrid}}=K_{\mathrm{ray}}-T_{\mathrm{direct}}\delta(\omega-\omega_i)+G_{\mathrm{gap}}(\omega),
\qquad \int G_{\mathrm{gap}}\,d\omega=T_{\mathrm{direct}}.
\]

The unchanged direct ray component must be removed before adding its diffracted replacement. Equivalently, keep the material-interaction term and replace only the explicitly separated uncollided contribution. Adding `G_gap` to a ray renderer that already transmits unoccluded camera/light rays duplicates energy. Subtracting it indiscriminately from total fabric transmission is also wrong: transmitted paths that encountered dielectric fibers are distinct from geometric pore misses.

**Current code is safe on this point:** the driver runs the FFT from `normal_visibility_mask` and saves metrics, without modifying any ray-rendered image. The outputs should therefore be labeled “geometry-derived direct-pore diffraction diagnostic.” They are not total BTDF, not wave-enhanced fabric images, and not the complete local Gaussian-beam ray-wave blend in Yu et al.

For the executed patches, normal projected open fractions are about 0.14256, 0.15370, and 0.15453 for plain/twill/satin. Fraunhofer total power for the point-source calculation equals these fractions up to roundoff. These are geometry-specific values, not universal porosities or total transmittances for each weave. The 1024² visibility grid has 1.60156 µm pitch; the final geometry-derived diffraction metrics do not inherit every convergence percentage established earlier for separate ideal rectangular masks.

Source-size averaging keeps the same normal projected mask and uses small-angle shifted intensities. It does not retrace the actual thick fabric silhouette for every incoming angle. Small changes in total angular power under blur are explicitly finite-window escape, not dye absorption. Three equally weighted wavelengths are a synthetic incident spectrum, not calibrated daylight or a complete colorimetric calculation.

## 6. Meta-optics coupling and information claims

The ideal phase pupil computes independent unit-clear-pupil-power responses. Its 4×9 matrix is a valid passive intensity operator within the scalar model, but there is no current mapping from the textile's emitted angular/spectral distribution into that clear-pupil field. A relay, pupil acceptance, spatial patch aperture, angular mapping, magnification, coherence, and detector spectral response must be specified before multiplying outputs from different modules.

The observed symmetric-rank2/asymmetric-rank4 result is a restricted design comparison for nine synthetic monochromatic angular hypotheses. It does not prove that four arbitrary spectra can be reconstructed, that fabric classes are separable, or that the corresponding phase can be fabricated with 80% efficiency. It is useful evidence that hardware channels should be evaluated by their independent response to the intended task, rather than by counting the number of image replicas. The assumed 0.8 throughput remains a chosen penalty, not a measurement.

The exact-cylinder field-intensity plots also cannot be passed directly into the incoherent camera MTF: a coherent image requires propagation of complex fields through a pupil before square-law detection. Conversely, the current camera operates on radiance/intensity images and contains no phase information. This distinction is especially important when integrating the finite-beam Maxwell experiment after its separate review is complete.

## 7. One additional targeted numerical check

The only new numerical experiment in this review checked a concrete camera-boundary risk: `optical_filter` uses edge extension with a fixed pad of 32 pixels. The stored 512² macro was re-filtered with pad32/pad64/pad128 at the same 1.5625 µm pitch. No path tracing or random detector noise was rerun.

| NA | Relative L2, pad32 vs pad128, whole frame | Same, central 384² | Relative L2, pad64 vs pad128, whole frame |
| --- | ---: | ---: | ---: |
| 0.02 | 0.1713% | 0.1241% | 0.0822% |
| 0.04 | 0.0828% | 0.0601% | 0.0398% |
| 0.08 | 0.0401% | 0.0292% | 0.0193% |

The remaining edge-extension/window effect is small for the present illustrative camera comparison. No code change or larger experiment is required to support its stated scope. Pad128 is a comparison, not an exact reference; these numbers should not be converted into a universal certified error bound.

The saved furnace snapshot was also read without rerunning or editing its in-progress validator. Unlimited-depth full mean was 0.998725, fully covered mean 0.998578, and corresponding across-seed standard errors about 0.000143/0.000184. Thus the approximately 0.13–0.14% residual is larger than those estimated errors. The report can state that the check approaches unit radiance closely while retaining that residual. It should not claim exact conservation within Monte Carlo uncertainty. Final validation output takes precedence over this snapshot.

## 8. Wording suitable for the main report

“We implemented exact 2D fiber/cluster electromagnetic benchmarks, an independent ply power-ray model, positive 2D angular compression, explicit-fiber 3D ray rendering, a geometry-derived direct-pore diffraction diagnostic, a conventional camera model, and an ideal meta-optics measurement emulator. Geometry is shared between the 3D renderer and the pore-mask calculation, and rendered radiance is passed to the camera model. The exact wave solver and meta-optics measurement matrix have not yet been coupled into a validated end-to-end fabric appearance reconstruction. Numerical tests establish behavior for the stated synthetic models; they do not validate real textile materials or a fabricated metasurface.”

That description is supported by the inspected code and executed artifacts. Claiming a full reproduction of DOI10.1145/3763359, realistic named-fiber material identification, wave-speckle cloth rendering, exact total R/T, or measured improvement over product photography would go beyond this work.
