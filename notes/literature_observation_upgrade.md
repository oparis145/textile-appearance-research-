# Fabric–optics literature audit and implementation decisions

Review date: 2026-10-13. Base repository: `d5ee2b7d4677f8b98f99bac821fec340ffe98c9c`.
This is an additional reading ledger, not a claim to have reproduced every paper.
No third-party paper, dataset, checkpoint, or source code is re-distributed here.
Existing v2/v3 reading ledgers and license notices remain authoritative for earlier work.

## Sources, reading depth and decisions

| Primary source | What was inspected in this update | Consequence for this update / next benchmark |
| --- | --- | --- |
| [Bergou et al., Discrete Elastic Rods, 2008](https://www.cs.columbia.edu/cg/rods/index.html) | Author overview; prior repository methods review retained, not re-executed | A moving frame and a radius rule are not a material twist/contact constitutive law. Do not call the new profile solver DER. |
| [Zhao et al., Fitting Procedural Yarn Models for Realistic Cloth Rendering, 2016](https://www.cs.cornell.edu/projects/ctcloth/) | Author project, CT fitting/flyaway description, code/data availability | Future parameters must be calibrated from measured structure. Synthetic profile cases are not cotton/silk data. |
| [Leaf et al., Interactive Design of Periodic Yarn-Level Cloth Patterns, 2018](https://graphics.stanford.edu/projects/yarnsim/) | Official overview and resources; full derivation not newly reproduced | Periodic boundary conditions and manufacturing topology stay separate from optical fidelity. |
| [Wu et al., Weavecraft, 2020](https://www.cs.cornell.edu/projects/weavecraft/) | Official overview; earlier topology audit retained | Multilayer stacks require connectivity, not an extra radius parameter. Deferred rather than renamed as implemented. |
| [Montazeri et al., Mechanics-Aware Modeling of Cloth Appearance](https://arxiv.org/pdf/1904.11116) | Accessible 14-page author manuscript: scale coupling, method overview, parameter fitting and limitations; Fig. 3 visually checked | Mechanics-to-appearance coupling is direct prior work. This update studies a narrow local-volume contract, not a new general mechanics-aware renderer. |
| [Sperl et al., Mechanics-Aware Deformation of Yarn Pattern Geometry, 2021](https://visualcomputing.ist.ac.at/publications/2021/MADYPG/) | Author low-resolution paper, material-coordinate/strain mapping and limits; method figure visually checked | Preserve material labels when transferring deformation. Interpolation, mechanics, and optical validity need different tests. |
| [Xia et al., A Wave Optics Based Fiber Scattering Model, 2020](https://mandyxia.com/research/wavefiber.html) | Author method overview, code link and stated approximation limits | 2.5D BEM for constant cross sections is a future non-circular reference. New first-surface code is geometric optics, not its reproduction. |
| [Montazeri et al., A Practical Ply-Based Appearance Model of Woven Fabrics, 2020](https://projects.shuangz.com/practical_cloth-sa20/) | Accessible 13-page low-resolution paper; geometry, reflection/transmission layers, normal/tangent/visibility maps; method page visually checked | Benchmark actual optical response, not just over-under order or projected-area fit. A strong ply baseline is required before claiming fiber detail is necessary. |
| [Yu et al., Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model, 2025](https://blaire9989.github.io/assets/3_RayWaveFabric/project.html) | Official project, abstract and model decomposition. Full paper/supplement fetch exceeded reader size limits in this update | Keep mean ray transport, instance variation and direct-gap diffraction separate. Do not claim full-paper implementation or add their energies blindly. |
| [Xia et al., Predicting Fabric Appearance Through Thread Scattering and Inversion, 2025](https://mandyxia.com/research/fabrix.html) | Official pipeline overview and code link. Large paper fetch failed; technical document timed out | Actual thread R/T calibration plus independent weave validation is the preferred measured-data path. Not run here. |
| [Tang et al., Woven Fabric Capture with a Reflection-Transmission Photo Pair, 2024](https://arxiv.org/html/2406.19398v3) | Accessible primary HTML: layered model, capture/recovery and limits. Repository's prior official-code audit retained | A simple RGB R/T baseline must be tested before metasurface complexity. No checkpoint or inverse fitting was run in this update. |
| [Khattar et al., A Multi-scale Yarn Appearance Model with Fiber Details](https://arxiv.org/abs/2401.12724) | Primary abstract/metadata; prior GitHub README review reports initial two-yarn scenes rather than all paper scenes | Yarn/ply alternatives are future performance baselines. Full numerical reproduction is not claimed. |
| [Yang et al., Real-time Woven Fabric Rendering Using SGGX Fitting, 2026](https://www.sciopen.com/local/article_pdf/10.26599/CVM.2025.9450445.pdf) | Accessible 13-page publisher paper, NDF mipmap/range query and fitting; p. 5 visually checked | Their footprint-dependent optical model is more than this repository's unoccluded projected-area diagnostic. New angular histogram test is not a replacement for their method. |
| [Li et al., PureSample, SIGGRAPH 2026](https://arxiv.org/html/2508.07240v3) | Primary HTML method/decomposition and discussion | Separate total reflected power from normalized distribution; neural aggregation remains a future comparator. No network trained here. |
| [Li et al., Fiber-level Woven Fabric Capture, TOG 2026](https://www.rendering-zixuan.com/paper_pages/FiberFabric/) | Current author publication metadata and overview | Do not recycle 2024-preprint limitations as verified current gaps. High-resolution microscopic recovery remains a strong baseline. |
| [Tang et al., FabricGen, CVPR 2026](https://arxiv.org/html/2603.07240v1) | Primary HTML overview, representation and goal | Generative plausibility is not the measured identity of a particular product. Not used as experimental ground truth. |
| [Garces et al., Towards Material Digitization with a Dual-scale Optical System, 2023](https://mslab.es/projects/DOME/) | Official micro/mesoscale capture overview; one older author URL failed | Future real-patch experiments must relate footprint, reflection/transmission and calibration across scales. |
| [Uncertainty for SVBRDF Acquisition using Frequency Analysis, 2025](https://svbrdf-uncertainty.github.io/) | Official method/uncertainty overview | Measurement selection is established prior art. New gates prevent numerical error from being selected as useful material information. |
| [MetaSpectra+, CVPR 2026](https://meta-imaging.qiguo.org/) | Official system description and channel roles | Channel count is not independent information. Actual throughput/crosstalk and conventional optics comparisons remain required. |

## What changed because of the review

1. **Fabric contract:** preserve each straight segment's declared volume before claiming physical transport; explicitly reject an infeasible continuous-radius state. Do not silently repair by changing total material.
2. **Optics contract:** geometrically accurate volume can coexist with a poor distribution of specular normals. Isolate first-interface reflection using a circular reference before diagnosing the full refractive fabric.
3. **Observation contract:** compare after a declared angular response and detector integration. Vary detector bin alignment and cross-section phase so that an accidental quadrature alignment does not pass as convergence.
4. **LOD contract:** equal integrated power is necessary but insufficient. Compare the observed distribution and a separate refinement diagnostic, then test conditions excluded from selection.
5. **Statistics contract:** a confidence interval containing zero does not establish practical equivalence. Use predeclared absolute tolerances and independent paired repeats; never count pixels as repeats.

These contracts are an incremental implementation based on the questions raised by the literature. They do not establish novelty over all prior work, a calibrated fabric BSDF, a finished 3D ray–wave bridge, or metasurface superiority.

## Future reproducibility baselines

Priority order: calibrated thread scattering -> RGB reflection/transmission recovery -> ply appearance -> footprint-dependent SGGX / multi-scale yarn -> wave correction only where observed differences survive.
For each future import record the upstream commit, license, complete dependency set, measured/synthetic split, actual execution, and whether all published scenes/checkpoints were available. A project website or code link alone is not an executed baseline.
