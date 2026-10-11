# Module: positive 2D angular compression

`textile_sim/angular_surrogate.py` compresses a ray-traced outgoing angular
distribution into a positive, normalized circular mixture. It is a diagnostic
between explicit cross-section transport and a compact transport kernel. It
does not construct a 3D BSDF, reproduce Yu et al.'s anisotropic spherical
Gaussian fit, or replace fiber geometry with a universal material descriptor.

## Representation and units

The continuous conditional density is a von Mises mixture

\[
 q(\theta)=\sum_{k=1}^{K}\pi_k
 \frac{\exp[\kappa_k\cos(\theta-\mu_k)]}{2\pi I_0(\kappa_k)},
 \qquad\pi_k\geq0,\quad\sum_k\pi_k=1,\quad\kappa_k\geq0.
\]

Its integral over 2pi is one and its unit is rad^-1. Multiplying by the
encountered, escaping continuous-power fraction gives an absolute power kernel.
Uncollided transmission and exactly undeviated encountered transmission remain
explicit delta terms at the incident direction. The second delta matters for
the index-matched test: encountered geometry must not acquire fictitious
broad scattering. Absorbed and unresolved power are retained unchanged as
separate scalar channels.

The continuous kernel, delta amplitudes, absorbed fraction and residual add
to incident power. This conservation is a property of the representation; it
does not establish angular accuracy. Backward/forward probabilities predicted
by a compressed mixture can differ from those of its training rays and are
evaluated independently on validation rays.

The mixture is never revolved into a 3D lobe. Such a transformation would need
solid-angle normalization, axial scattering, polarization treatment and
reciprocity that are not supplied by a 2D circular probability density.

## Fitting algorithm

Training ray angles are binned into 720 bins covering [-pi,pi), with each bin's
center and ray-power count serving as a weighted circular observation. This
is a fine-bin approximation to the unbinned likelihood, explicitly separate
from the 360-bin validation histogram. The energy amplitudes are taken from
actual ray weights, with no artificial redistribution of missing power.

Weighted expectation–maximization (EM) computes component responsibilities and
updates each mean from a circular resultant. The concentration solves

\[
 I_1(\kappa_k)/I_0(\kappa_k)
 =\left|\sum_j r_{jk}w_j e^{i\theta_j}\right|/\sum_j r_{jk}w_j.
\]

The implementation uses scaled Bessel functions and a bounded Newton inverse.
Concentrations are capped at 512, corresponding to a narrow-lobe Gaussian
approximation with standard deviation about 2.53 degrees. This cap prevents
arbitrarily sharp component collapse; it also limits how well the mixture can
represent narrow caustics. The density is evaluated using log-sum-exp, so no
negative lobes or subtractive coefficients are needed. Bin probabilities use
the circular CDF rather than midpoint density times bin width.

Four initializations are selected using training likelihood only. The current
study allows 600 EM iterations with a 1e-10 per-observation likelihood tolerance.
The one-component case meets that tolerance. The 4-, 8- and 16-component cases
hit the iteration cap, with final likelihood increments about 2.12e-8,
9.11e-8 and 2.01e-6. Their recorded models are finite-budget fits, not certified
optima. All selected-run likelihood sequences were nondecreasing within the
tested numerical tolerance. No validation metric selects a restart or a
different training iteration.

## Experiment actually executed

The same synthetic 19-fiber geometry as the ray module is used: radius 5 um,
gap 0.4 um, index 1.55, host index 1, unpolarized plane-parallel incidence +x.
The mixture is trained on 200,000 rays with RNG seed 5101 and tested on a
separate 200,000-ray trace with seed 7202. The two sets are neither reused
histograms nor neighboring pixels from one image. They do share the same
geometry: this evaluates compression of that geometry's transport, not
generalization to an unseen textile or another illumination direction.

The validation ray backward fraction is 0.278745. Here all input rays encounter
geometry, so the uncollided amplitude is zero; the explicit-delta behavior is
checked separately in unit tests with a wider beam and index-matched fibers.

| Mixture components | JS divergence (nats) | Maximum CDF error | Binned L1 error | Predicted backward fraction |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0696571 | 0.120204 | 0.678609 | 0.250316 |
| 4 | 0.00917525 | 0.0124568 | 0.212100 | 0.281836 |
| 8 | 0.00609977 | 0.00467560 | 0.163891 | 0.275226 |
| 16 | 0.00405922 | 0.00473996 | 0.131535 | 0.279455 |

JS divergence between the two uncompressed empirical ray histograms is
0.000451883. The compression error thus remains above the finite-sampling
discrepancy, even with 16 lobes. The 16-component backward probability differs
from validation by 0.000710, but its binned L1 error is still 0.131535; correct
hemispherical power does not imply a detailed angular match. The 8-component
model has a slightly smaller maximum CDF error than the 16-component model.
Additional components improve the reported JS metric here, not every metric
monotonically.

The 16-component conditional shape has 47 independent parameters
(16 means, 16 concentrations, 15 independent weights), compared with the 720
training bins. This is a compact numerical representation of the measured
synthetic kernel; it is not a guarantee that these parameters identify an
actual fiber type, twist, refractive index or material composition.

## Checks and delivered outputs

Five tests cover continuous positivity and normalization, circular periodicity,
known two-lobe recovery, nondecreasing EM likelihood, preservation of absorbed
power and delta amplitudes, and JS divergence limits. An index-matched cylinder
keeps a pure forward delta rather than acquiring a finite-width lobe.

Reproduce from `textile_lab`:

```sh
OPENBLAS_NUM_THREADS=1 python -m unittest discover -s tests -p test_angular_surrogate.py -v
OPENBLAS_NUM_THREADS=1 python -m textile_sim.angular_surrogate
```

Outputs:

- `data/ply_ray_surrogate_models.json`: mixture and energy parameters.
- `data/ply_ray_surrogate_metrics.json`: training histories, seeds, termination
  conditions and independent-validation errors.
- `data/ply_ray_surrogate_distributions.npz`: full validation/training/model
  bin probabilities, suitable for independent plots or alternative metrics.
- `data/ply_ray_surrogate_overview.png`: visualization generated from those
  outputs and inspected for layout.

The mathematical density and circular CDF conventions can be checked against
the official SciPy documentation:
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.vonmises.html
The EM code is an independent implementation of the mixture likelihood.
