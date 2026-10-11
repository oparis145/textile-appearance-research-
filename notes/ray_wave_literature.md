# Literature and public-code audit

Read on 2026-10-10. This codebase is an independent research prototype. It does
not reproduce the complete Yu2025 renderer or report a fit to measured cloth.
No source code from the repositories below was copied into `aperture_wave.py`.

## Yu et al., Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model

- DOI: https://doi.org/10.1145/3763359
- Author project: https://blaire9989.github.io/assets/3_RayWaveFabric/project.html
- Paper: https://blaire9989.github.io/assets/3_RayWaveFabric/paper.pdf
- Supplemental: https://blaire9989.github.io/assets/3_RayWaveFabric/supplemental.pdf

The main PDF was downloaded successfully (12,867,606 bytes). It contained no
usable text layer; core methods and discussion, pages2–14, were read through OCR.
The project linked a paper and supplemental; targeted searches did not identify
a released implementation. The 75MB supplement was identified, not fully read.

Method map: multi-object2D BEM references untwisted plies. Agreement of50-instance
averages motivates3D ray tracing of twisted plies. Gaussian beam waist:10um.
Missed-ray energy feeds diffraction, instead of retaining delta transmission.
One ASG fits reflection;8 ASGs fit higher orders, with coupled3×3 incident blocks.
Inter-ply convolution and geometric-series residuals extend the model. Local
Gaussian-windowed rectangular Kirchhoff apertures handle gaps and ply edges.
Wave simulations calibrate correlated, unit-mean speckle noise. The shader uses
Mitsuba3. The authors still observe excessive transmission and assume circular
plies/ideal helices. Their tiny-gap organza color demonstration uses a heuristic
25/75 mixture, explicitly outside the formal model.

**Our mapping:** the finite-mask FFT and Gaussian-beam option investigate a
subset of the aperture mechanism. They omit general-incidence obliquity, local
ply-edge fitting, coupled ASG models, and wave-calibrated noise. Existing ray
transport plus our FFT is therefore not the published hybrid BSDF.

## Xia et al., A Wave Optics Based Fiber Scattering Model (2020)

- Primary project: https://mandyxia.com/research/wavefiber.html
- Simulation code: https://github.com/mandyxmq/WaveOpticsFiber
- Rendering code linked by authors: https://github.com/mandyxmq/WaveOpticsFiberRendering

The primary paper project and simulation README were inspected. The simulation
uses BEM for a straight infinite dielectric cylinder of arbitrary cross section;
oblique incidence is a2.5D electromagnetic problem. It exports angular scattering
and extinction/absorption quantities. Build dependencies include Eigen3, OpenMP,
complex_bessel, and an externally hosted Hankel table. This scope differs from
finite, mutually twisted fibers. A circular-cylinder analytic implementation is
an independently solvable reference case, not a reproduction of arbitrary-shape
BEM. Repository direction conventions place forward azimuth at pi; local code
must document its own convention when comparing distributions.

## Xia et al., A Practical Wave Optics Reflection Model for Hair and Fur (2023)

- Simulation/fitting code: https://github.com/mandyxmq/WaveFiber3d

The README and directory map were inspected. A CUDA/cuFFT hierarchical physical-
optics approximation computes3D scattering, followed by a fitted wavelet-noise
representation. Included comparisons use2D BEM,3D BEM, and Mie references. This
is a useful architecture for future irregular-fiber simulations, but it is neither
a general Maxwell solver nor a cloth forward model that can be substituted
without checking its reflection assumptions and coupling to transmission.

## Tang et al., Woven Fabric Capture with a Reflection-Transmission Photo Pair (2024)

- Primary project: https://wangningbei.github.io/2024/FabricBTDF.html
- Code: https://github.com/lxtyin/FabricBTDF-Recovery
- Paper: https://arxiv.org/html/2406.19398v3

The public repository, README, and render-file structure were inspected. Its
GPL3 implementation uses PyTorch differentiable two-layer fabric shading with
SGGX/ASGGX, learned initialization, then optimization. The README specifies
PyTorch2.0/CUDA11.8 and supplied pattern maps; checkpoint download is external.
This is a complementary coarse/fitted BSDF baseline. It is not the2025 ray-wave
implementation, nor evidence that a new synthetic fiber model matches a real
fabric. No checkpoint training or published photo-pair recovery was claimed here.

## Design consequences for this prototype

1. Every module declares its geometry and coherence assumptions.
2. Numerical conservation is separate from real-material validation.
3. Diffraction redistributes the existing unblocked transmission budget.
4. Spectra/source positions are averaged as intensities unless coherence is
   explicitly retained in an incident field.
5. Fiber, ply and cloth simulations remain distinct until an effective-kernel
   handoff is actually implemented and checked for double counting.
