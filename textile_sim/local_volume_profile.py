"""Positive continuous radius reconstruction with per-segment frustum volumes.

This is a geometric alternative to the v5 global-volume rescaling rule. It
preserves EACH straight-chord frustum integral, not the volume of a bent tube
mesh, and supplies no elastic/contact constitutive law. Some input volumes
have no positive continuous piecewise-linear-radius solution: reject them.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar


def frustum_volumes(lengths, node_radii):
    l, r = np.asarray(lengths, dtype=float), np.asarray(node_radii, dtype=float)
    if (l.ndim != 1 or r.shape != (len(l)+1,) or len(l) < 1
            or not np.isfinite(l).all() or not np.isfinite(r).all()
            or np.any(l <= 0) or np.any(r <= 0)):
        raise ValueError('positive finite lengths and one more positive node radius required')
    return np.pi*l*(r[:-1]**2+r[:-1]*r[1:]+r[1:]**2)/3


def global_volume_baseline(lengths, segment_radii):
    """Reimplementation of the documented v5 interpolation rule for comparison.

    This function does not import, execute, or claim to replace the v5 adapter.
    """
    l, r = _inputs(lengths, segment_radii)
    v = np.pi*l*r*r
    nodes = np.r_[r[0], np.sqrt((l[:-1]*r[:-1]**2+l[1:]*r[1:]**2)/(l[:-1]+l[1:])), r[-1]]
    nodes *= np.sqrt(v.sum()/frustum_volumes(l, nodes).sum())
    return nodes


def _inputs(lengths, radii):
    l, r = np.asarray(lengths, dtype=float), np.asarray(radii, dtype=float)
    if (l.ndim != 1 or l.shape != r.shape or not len(l)
            or not np.isfinite(l).all() or not np.isfinite(r).all()
            or np.any(l <= 0) or np.any(r <= 0)):
        raise ValueError('equal nonempty positive finite length/radius vectors required')
    return l, r


def reconstruct_local_volume(lengths, segment_radii, *, minimum_radius_fraction=1e-8,
                             relative_volume_tolerance=1e-9):
    """Solve r_i^2+r_i*r_(i+1)+r_(i+1)^2=3*R_i^2 with positive radii.

    The decreasing involution f_i(x)=(-x+sqrt(12R_i^2-3x^2))/2 maps either
    endpoint radius to the other. Backward interval propagation finds feasible
    starting radii; a scalar bounded objective selects a nearby smooth profile.
    Feasibility and volume residuals are checked independently of optimizer
    success. The objective is a tie-breaker, not an asserted global optimum.
    Internally radii are scaled to avoid dependence on length-unit choice.
    """
    l, r = _inputs(lengths, segment_radii)
    for x, name in ((minimum_radius_fraction, 'minimum_radius_fraction'),
                    (relative_volume_tolerance, 'relative_volume_tolerance')):
        if isinstance(x, bool) or not np.isfinite(x) or not 0 < x < 1:
            raise ValueError(name+' must be finite and in (0,1)')
    scale = float(np.median(r))
    R = r/scale
    if np.max(R)/np.min(R) > 1e6:
        raise ValueError('radius dynamic range exceeds declared numeric domain')
    eps = float(np.min(R)*minimum_radius_fraction)

    def next_radius(x, radius):
        disc = 12*radius*radius-3*x*x
        if disc < -1e-12*radius*radius:
            raise ValueError('infeasible endpoint radius')
        root = np.sqrt(max(0., disc))
        # Rationalized form avoids cancellation when the next radius is small.
        return (6*radius*radius-2*x*x)/(root+x)

    low, high = eps, np.inf
    intervals = []
    for radius in R[::-1]:
        cap = next_radius(eps, radius)
        y0, y1 = max(eps, low), min(cap, high)
        if y0 > y1:
            raise ValueError('no positive continuous linear-radius profile for these segment volumes')
        low, high = max(eps, next_radius(y1, radius)), min(cap, next_radius(y0, radius))
        if low > high:
            raise ValueError('numerically empty feasible-radius interval')
        intervals.append((low, high))

    target = global_volume_baseline(l, r)/scale
    weights = np.r_[l[0]/2, (l[:-1]+l[1:])/2, l[-1]/2]
    weights /= weights.sum()

    def propagate(first):
        out = np.empty(len(R)+1)
        out[0] = first
        for i, radius in enumerate(R):
            out[i+1] = next_radius(out[i], radius)
        return out

    def objective(first):
        try:
            nodes = propagate(first)
            if not np.isfinite(nodes).all() or np.any(nodes <= 0):
                return np.inf
            return float(np.dot(weights, (nodes-target)**2))
        except ValueError:
            return np.inf

    if high-low > 1e-12:
        result = minimize_scalar(objective, bounds=(low, high), method='bounded',
                                 options={'xatol': 1e-13, 'maxiter': 500})
        choices = [float(result.x), .5*(low+high), float(np.clip(target[0], low, high))]
    else:
        choices = [.5*(low+high)]
    first = min(choices, key=objective)
    nodes = propagate(first)*scale
    expected = np.pi*l*r*r
    actual = frustum_volumes(l, nodes)
    errors = actual/expected-1
    if np.max(np.abs(errors)) > relative_volume_tolerance:
        raise ArithmeticError('local frustum-volume residual exceeds tolerance')
    return {'node_radii': nodes, 'segment_volumes': actual,
            'relative_segment_volume_error': errors,
            'initial_radius_interval': (low*scale, high*scale),
            'objective': objective(first),
            'minimum_radius': float(nodes.min()),
            'max_relative_volume_error': float(np.max(np.abs(errors))),
            'scope': 'straight-chord frustum integrals only; not bent mesh volume or a constitutive law'}
