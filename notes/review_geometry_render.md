# Independent geometry/render review

Reviewer: separate aperture-wave/literature agent,2026-10-10. Reviewed the current
`geometry.py`, `render.py`, their unit tests, and the pinned Mitsuba hair source.
The root implementation was not edited by this reviewer. Production render
validation outcomes belong to the run manifests, not to this static review.

## Findings communicated and addressed by the root workflow

###1. Geometry needs continuous separation checks

Checking yarn centers at crossings, or sampled fiber centers, is insufficient:
crimp can bring different fibers together between samples. The root independently
found collisions at tighter yarn pitches before production. The revised
`certify_spline_clearance` audits the actual uniform cubic B-spline geometry,
using a conservative capsule enclosure per segment.

I checked the proof and implementation:

- The cardinal B-spline to Bezier conversion is algebraically correct.
- A cubic Bezier lies inside the convex hull of its four controls. A line-segment
  capsule is convex. Inflating its endpoint chord by the largest control-to-chord
  distance encloses the entire curve.
- Adding the physical constant radius encloses the entire fiber tube segment.
- DeCasteljau subdivision preserves the curve and tightens the enclosure.
- The KD-tree search radius `2*max(inflated_radius)+max(chord_length)+margin`
  cannot omit a pair with surface clearance below the margin, by the triangle
  inequality applied to the two chord midpoints.
- A negative lower bound is an unresolved certificate, not proof of collision.

Independent numerical checks were executed using different formulations:

| Check | Observed result |
|---|---:|
|250 random/parallel/degenerate segment pairs against box-constrained least squares|maximum distance difference3.621e-12mm|
|Direct cardinal B-spline basis versus converted Bezier basis|maximum coordinate difference5.552e-17mm|
|Known orthogonal crossing of4um-radius fibers|certificate fails, lower bound−8um|
|Known parallel fibers,12um center spacing,4um radii|certificate passes, lower bound4um|

These checks support the implementation and its mathematical enclosure. Floating-
point tolerances should be kept far below the reported positive margins. The
certificate explicitly excludes same-fiber local/nonlocal self-intersections;
it must not be described as a proof of all possible textile contact constraints.
The generated cloth is prescribed geometry, not an equilibrium weave-mechanics
solution, and does not infer yarn flattening or tension from a real textile.

###2. Use the actual spline visibility mask for diffraction

`project_gap_mask` is a convenient raster illustration, but its PIL line-width
rounding is not guaranteed conservative and its output is fractional open area.
Directly using that fraction as a coherent amplitude produces `mean(gap²)`
instead of `mean(gap)` power. The root selected `normal_visibility_mask`, which
casts binary visibility rays against the actual rendered splines. This removes
the geometry and amplitude-interpretation mismatch. Its raster resolution still
needs to be reported and refined when small gaps affect the result.

###3. Absorption units require the pinned shader source

Inspected source:
https://raw.githubusercontent.com/mitsuba-renderer/mitsuba3/v3.9.1/src/bsdfs/hair.cpp

The implementation's internal fiber chord is normalized by radius:
`2 cos(gamma_t)/cos(theta_t)`. The texture absorption value is multiplied directly
by this dimensionless chord. Thus the wrapper's `sigma_a = mu_per_mm * radius_mm`
is consistent with physical Beer attenuation for its assumed circular fibers.
This was independently confirmed from the tagged source, including its pigment
coefficient comment and absorption evaluator. The prose documentation's inverse-
scene-unit wording alone would yield an incorrect scale here.

Because this conversion depends on3.9.1 behavior, require that version when
loading the renderer, or re-audit the source before allowing another version.
The function originally preferred any already-installed Mitsuba; a runtime
version guard is recommended in addition to pinned requirements.

###4. The higher-scale model is a ray BCSDF baseline

The hair plugin implements Chiang2016 near-field fiber scattering and collapses
internal fiber paths into a BSDF interaction. Its source marks it `NonSymmetric`.
Do not claim it is a direct injection of exact2D cylinder scattering, a general
Maxwell solution, or guaranteed pointwise reciprocal BRDF data. The explicit
scene does trace multiple interactions between separate fiber curves.

Changing generic roughness, twist or fixed index is a synthetic sensitivity
experiment; these parameters do not establish a calibrated silk/cotton/cupra
material identity. No dye model is introduced.

## Verification gates recommended for the production results

1. Run the lossless white furnace with fixed unit environment radiance. Report
   mean/error on pixels covered by fibers (preferably interior/core pixels) as
   well as the full frame. Empty gaps directly see the environment, so an
   excellent whole-frame mean could hide a fiber-shading problem.
2. Compare multiple sample counts and independent seeds on linear radiance.
   Never assess numerical convergence only after display clipping or sRGB.
3. Increase path depth for the denser/transmissive cases until the actual target
   image metrics stabilize; unlimited depth plus Russian roulette is useful as
   a reference, but stochastic error remains.
4. Refine axial curve sampling and binary visibility resolution for selected
   scenes. A positive clearance certificate alone does not guarantee that a
   coarse B-spline approximates the intended helix accurately enough.
5. Keep source geometry, view, exposure and display transforms identical for
   each geometry/material comparison. Current finite square-light irradiance
   normalization is a small-angle approximation; use a measured reference if
   comparing light sizes at strictly equal illumination budgets.

The root adopted binary Embree visibility and covered-pixel furnace reporting,
and is using a fixed7° rectangular source half width for the principal images.
The earlier `light_sigma_deg` name was misleading because that source is not
Gaussian; it should be renamed `light_halfwidth_deg`. Aperture-module Gaussian
source sigma and renderer rectangular half width must never be presented as the
same parameter without an explicit conversion/model comparison.

## Integration boundary

The aperture diffraction experiment should receive the binary direct-visibility
mask and its physical micrometre spacing. It redistributes only the unblocked
direct-transmission power. The current module does not replace the renderer's
full fiber-scattered transmission. Showing its angular result alongside a ray
render is scientifically appropriate if that boundary is explicit; adding both
direct terms would double count photons.
