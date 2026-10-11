# Independent review of the circular-fiber wave module

Reviewed module: `textile_sim/fiber_wave.py` and `tests/test_fiber_wave.py`.
Review was performed by the independently implemented power-ray module author.
No critical sign, normalization, polarization or absorption error was found in
the inspected and executed regimes. This is a numerical and mathematical
review, not validation against measured fibers or a reproduction of the
ray–wave cloth paper.

## Algebra and convention review

The time convention exp(-i omega t), outgoing Hankel-1 waves and passive
Im(n)>=0 are mutually consistent. Ez uses continuous scalar field and ordinary
normal derivative, whereas Hz uses the epsilon-weighted derivative; therefore
the respective interior derivative factors m and 1/m are correct when the
host index is one and all relative permeabilities are one.

The diagonal T coefficient is defined for `J_n + t_n H_n`. With that sign,
lossless passivity requires Re(t_n)+|t_n|^2=0; the negative sign in
`Cext = -(4/k) Re sum(t_n)` is therefore correct. The single-fiber far-field
normalization yields `dCsca/dtheta=2|F|^2/(pi*k)` and
`Csca=(4/k) sum |t_n|^2`. These are cross sections per unit cylinder length,
with dimension length, not a 3D cross section or a normalized BSDF.

For the cluster, raw outgoing coefficients include the plane-wave angular
factor i^n. The far-field factor (-i)^n cancels it in the one-cylinder limit.
The translation matrix uses `H_(m-n)(k|c_j-c_l|) exp(i(m-n) beta_jl)` and the
external-source field is added before the local T operation. The surface-Hankel
scaling is a change of unknowns and does not alter the scattering problem.

The optical-theorem extinction, far-field scattering quadrature and local
boundary flux are separately evaluated. The code neither clips negative
absorption nor rescales scattering to force conservation. Existing tests also
correctly recognize that conservation alone cannot prove modal convergence.

## Additional independent checks executed

The records are in `data/ply_ray_review_wave.json`.

### 1. Graf translation against a direct outgoing cylindrical wave

For source (-0.7,0.2) um, target (0.4,0.7) um and an observation circle of
radius 0.2 um around the target, the translated expansion with n=-35..35 was
compared with direct Hankel evaluation for outgoing source orders m=-3,0,4.
The wavelength was 0.55 um and 91 observation points were used.

| Source order | Relative L2 error |
| --- | ---: |
| -3 | 2.263e-15 |
| 0 | 2.202e-15 |
| 4 | 1.959e-15 |

This specifically checks the translation index/sign and position phase. It is
independent of the cluster solver's energy identities.

### 2. Absorption from a volume Joule-loss integral

A deliberately heterogeneous two-fiber cluster used centers (-0.2,0.1) and
(0.7,0.33) um; radii 0.25 and 0.33 um; indices 1.55+0.03i and 1.42+0.05i;
wavelength 0.55 um; incidence 0.31 rad; maximum modal order 24.

For Ez normalized to incident electric amplitude, absorption is independently
computed from

\[
 C_{\rm abs}^{Ez}=\sum_j k_0\operatorname{Im}(\epsilon_j)
 \int_{A_j}|u|^2\,dA.
\]

For Hz normalized to incident magnetic amplitude, Maxwell's electric-field
relation gives

\[
 C_{\rm abs}^{Hz}=\sum_j
 \frac{\operatorname{Im}(\epsilon_j)}{k_0|\epsilon_j|^2}
 \int_{A_j}|\nabla u|^2\,dA.
\]

Here epsilon_j=n_j^2. Hz gradients were evaluated by centered Cartesian finite
differences of the field evaluator with step 1e-6 um, rather than by reusing
the module's local-flux formula. Gauss–Legendre radial integration and uniform
angular integration were doubled from 24×96 to 48×192 points per fiber.

| Quantity | Ez | Hz |
| --- | ---: | ---: |
| Global optical-theorem Cabs (um) | 0.383647937873 | 0.407560997150 |
| Volume absorption, fiber 1 (um) | 0.175668062342 | 0.149722957997 |
| Volume absorption, fiber 2 (um) | 0.207979875530 | 0.257838039127 |
| Relative volume/global discrepancy | 7.669e-15 | 6.552e-11 |
| Relative change on integration-grid doubling | 4.341e-16 | 1.422e-12 |

The finite-difference Hz discrepancy is consistent with its additional
numerical differentiation. Agreement checks passive-index signs, interface
polarization factors, physical units and internal-field coefficients together.

### 3. Units and reciprocity on the same absorbing heterogeneous geometry

All positions, radii and wavelength were scaled by 1000. Cross sections scaled
by 1000, with relative discrepancies 3.22e-15 (Ez) and 3.44e-15 (Hz).

The reciprocal amplitude was compared under
`F(theta_out,theta_in) = F(theta_in+pi,theta_out+pi)` with theta_out=0.4 rad.
Relative discrepancies were 4.06e-16 (Ez) and 6.91e-16 (Hz). Loss does not break
reciprocity for these scalar isotropic nonmagnetic materials.

## Remaining limits and recommended gates

- The formulas are exact for their idealized two-dimensional geometry, but the
  finite modal expansion and floating-point special functions still require
  convergence checks for each larger radius, smaller gap or high contrast.
- Boundary coefficient residuals alone do not capture the error caused by
  truncating the incident plane wave or the coupling expansion. The existing
  physical-surface field/derivative tests and N versus N+8 comparisons should
  remain required for the textile-scale cluster run.
- Bessel/Hankel values can overflow at extreme modal orders or parameter
  values. The module detects nonfinite coefficients; scaled special functions
  or a logarithmic formulation would be required beyond the tested regime.
- The default host is fixed to n=1. It must not be called with a relative
  index while interpreting wavelength as the wavelength in an arbitrary host
  without an explicit change of units and power normalization.
- An exact scattered-field cross section must not be equated to an
  intercepted-ray power cross section. The missing forward diffraction and
  incident-field interference are material in wave/ray comparisons.
- Averaging wavelength and illumination angle must average intensities for
  mutually incoherent sources. The module implements that convention. It does
  not imply a model of partial spatial coherence between arbitrary points.

The results support using this wave module as a reference for synthetic
single-cylinder and finite parallel-cylinder cross sections. They do not by
themselves establish a full three-dimensional yarn, garment renderer or
real-fabric appearance prediction.
