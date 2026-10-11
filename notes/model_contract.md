# Textile optical simulation v1: scope and interface contract

Date: 2026-10-10. The current task explicitly excludes dyeing and fading. All refractive indices and absorption parameters are controlled synthetic inputs, not measured values assigned to silk/cotton/linen.

## Coordinate systems and units
- Fiber and ply: lengths in micrometers, infinite cylinder axis z, incoming propagation +x in the xy plane, far-field angle theta from +x. Time convention exp(-i omega t), outgoing Hankel1, passive n has Im(n)>=0. Ez corresponds s; Hz corresponds p at normal incidence.
- Cloth geometry: lengths in millimeters, cloth in xy plane, warp follows y and weft x, top normal +z. All units converted explicitly at module boundaries.
- Diffraction: aperture-plane x/y; paraxial angular coordinates in radians; wavelength and pixel spacing in micrometers. Incoherent source/wavelength samples add intensities.
- Camera: linear radiance is saved before a single fixed exposure and sRGB encoding. Do not compare independently autoexposed pictures quantitatively.

## Model responsibilities
1. Exact single and small-cluster Maxwell solutions are a 2D electromagnetic benchmark, not a full 3D fabric solver.
2. Explicit ray intersections/Fresnel events handle ply mean transport; finite ray budgets expose residual/truncation and Monte Carlo uncertainty. Maxwell scattered-field cross section is not equal to geometrically intercepted outgoing power.
3. Geometric yarn/fiber assemblies and a published ray optical BCSDF feed high-level fabric path tracing. Any fitted/effective kernel is labeled separately; a two-dimensional phase function is not silently used as a reciprocal 3D BSDF.
4. Fraunhofer gap diffraction replaces only direct aperture transmission and has its own validity domain. Raw coherent far-field patterns are not normal room-light photographs.
5. The camera module explicitly handles spatial averaging/noise/sampling. No synthetic result validates actual textile appearance without independent measured fabrics.

## Validation gates
Energy/cross-section identities; n=1 limits; passivity; expansion/angular/grid/sample convergence; analytic slit zeros; geometry over-under/contact and coverage; integrator depth and spp checks; fixed seeds/configuration capture. Independent review must record any corrected defect and remaining limitation.
