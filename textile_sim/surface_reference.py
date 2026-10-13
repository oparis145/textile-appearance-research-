"""First-surface cylinder/polygon reflection oracle, not a textile BSDF.

The infinite fiber axis is z; illumination and outgoing angles lie in xy.
Powers are normalized by incident flux through the SAME circumscribed width 2R.
No internal reflection, absorption, inter-fiber visibility, or wave effect is
included. Circle angles are quadrature-integrated; polygon power uses actual
face normals and conservative angular deposition. Finite grids need refinement.
"""
from __future__ import annotations

import numbers
import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.special import roots_hermitenorm

TAU = 2.0 * np.pi


def _integer(x, name, minimum=1):
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Integral) or x < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return int(x)


def _real(x, name, minimum=0.0):
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, numbers.Real):
        raise ValueError(f'{name} must be a real number')
    x = float(x)
    if not np.isfinite(x) or x < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    return x


def _power(x):
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) < 4 or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError('power must be a finite, nonnegative 1D array of length >= 4')
    return x


def fresnel(cosine, n_inside=1.55, polarization='u'):
    """Exterior n=1, real interior n>=1; exact s/p power Fresnel coefficients."""
    n = _real(n_inside, 'n_inside', 1.0)
    if polarization not in ('s', 'p', 'u'):
        raise ValueError('polarization must be s, p, or u')
    c = np.asarray(cosine, dtype=float)
    if not np.isfinite(c).all() or np.any(c < 0) or np.any(c > 1):
        raise ValueError('cosine must lie in [0,1]')
    if n == 1.0:
        return np.zeros_like(c)
    ct = np.sqrt(np.maximum(0., 1. - (1. - c*c)/(n*n)))
    rs = ((c-n*ct)/(c+n*ct))**2
    rp = ((n*c-ct)/(n*c+ct))**2
    return rs if polarization == 's' else rp if polarization == 'p' else (rs+rp)*.5


def _source(sigma_deg, order, center):
    sigma = _real(sigma_deg, 'source_sigma_deg')
    order = _integer(order, 'source_order', 3)
    center = float(center)
    if not np.isfinite(center) or sigma > 15:
        raise ValueError('finite center and source sigma <=15 deg required')
    if sigma == 0:
        return np.array([center]), np.array([1.])
    x, w = roots_hermitenorm(order)
    return center + np.deg2rad(sigma)*x, w/np.sqrt(TAU)


def _deposit(angles, weights, size):
    """Cloud-in-cell on periodic BIN CENTERS; preserves power, not sharp detail."""
    q = np.mod(angles, TAU)/(TAU/size)-.5
    i = np.floor(q).astype(np.int64)
    t = q-i
    return (np.bincount(np.mod(i, size), weights=weights*(1-t), minlength=size)
            + np.bincount(np.mod(i+1, size), weights=weights*t, minlength=size))


def surface_power(*, sides=None, grid_size=8192, phase_rad=0., n_inside=1.55,
                  polarization='u', source_sigma_deg=0., source_order=81,
                  source_center_rad=0., circle_order=4):
    """Return angular bin powers and budget for a circle or inscribed polygon.

    For the circle p(psi)=sin(psi/2)*F(sin(psi/2))/4 at normal-plane incidence.
    Polygon facet weight is sin(pi/N)*max(-d.n,0)*F(-d.n). We never rescale its
    smaller silhouette or renormalize reflected power to match the circle.
    A finite source is a Gaussian distribution of transverse propagation angles
    at equal incident power per common reference aperture, NOT a 3D area lamp.
    """
    size = _integer(grid_size, 'grid_size', 32)
    order = _integer(circle_order, 'circle_order', 2)
    phase = float(phase_rad)
    if not np.isfinite(phase):
        raise ValueError('phase_rad must be finite')
    n = _real(n_inside, 'n_inside', 1.0)
    phi, sw = _source(source_sigma_deg, source_order, source_center_rad)
    step = TAU/size
    centers = (np.arange(size)+.5)*step
    result = np.zeros(size)
    intercepted = 0.
    if sides is None:
        x, w = leggauss(order)
        points = centers[:, None] + .5*step*x
        for angle, weight in zip(phi, sw):
            c = np.sin(np.mod(points-angle, TAU)*.5)
            mass = .5*step*((.25*c*fresnel(c, n, polarization))@w)
            # Split the one bin crossing the periodic forward-direction cusp.
            # Without this, source rotation introduces a small quadrature bias.
            j = int(np.floor(np.mod(angle, TAU)/step)) % size
            lo = float(np.mod(j*step-angle, TAU))
            if lo+step > TAU and lo > 1e-14:
                pieces = ((lo, TAU), (0., lo+step-TAU))
                mass[j] = 0.
                for left, right in pieces:
                    cc = np.sin((.5*(left+right)+.5*(right-left)*x)*.5)
                    mass[j] += .5*(right-left)*float((.25*cc*fresnel(cc, n, polarization))@w)
            result += weight*mass
        intercepted = 1.
    else:
        sides = _integer(sides, 'sides', 3)
        normals = phase+(np.arange(sides)+.5)*TAU/sides
        for angle, weight in zip(phi, sw):
            c = np.maximum(-np.cos(normals-angle), 0.)
            area = np.sin(np.pi/sides)*c
            outgoing = 2*normals-angle+np.pi
            result += weight*_deposit(outgoing, area*fresnel(c, n, polarization), size)
            intercepted += weight*float(area.sum())
    reflected = float(result.sum())
    if reflected > intercepted + 2e-12 or intercepted > 1.+2e-12:
        raise ArithmeticError('first-interface energy budget violated')
    return result, {
        'intercepted': float(intercepted), 'reflected': reflected,
        'entered_untraced': float(max(0., intercepted-reflected)),
        'missed': float(max(0., 1.-intercepted)),
        'area_ratio': 1. if sides is None else float(sides*np.sin(TAU/sides)/TAU),
        'model': '2D first exterior Fresnel reflection only',
    }


def observe(power, *, sigma_deg, detector_bins=256):
    """Wrapped Gaussian ANGULAR instrument response then finite-bin integration.

    This is not spatial camera blur, photon noise, or a full 3D camera model.
    A nonzero sigma must span >=2 fine-grid steps. Grid refinement is still
    mandatory; the sampled response is normalized to preserve incident power.
    """
    p = _power(power)
    bins = _integer(detector_bins, 'detector_bins')
    sigma = _real(sigma_deg, 'sigma_deg')
    if len(p) % bins or sigma > 15:
        raise ValueError('detector_bins must divide grid_size and sigma <=15 deg')
    width = np.deg2rad(sigma)
    if width and width < 2*TAU/len(p):
        raise ValueError('angular response is under-resolved; refine grid')
    if width:
        distance = np.minimum(np.arange(len(p)), len(p)-np.arange(len(p)))*TAU/len(p)
        kernel = np.exp(-.5*(distance/width)**2)
        kernel /= kernel.sum()
        out = np.fft.irfft(np.fft.rfft(p)*np.fft.rfft(kernel), n=len(p))
        if out.min() < -1e-13*max(1., p.sum()):
            raise ArithmeticError('negative convolved power beyond roundoff')
        out = np.maximum(out, 0.)
    else:
        out = p.copy()
    return out.reshape(bins, -1).sum(axis=1)


def angular_lod(power, groups):
    """Conservative piecewise-uniform angular approximation; not a ply BSDF."""
    p = _power(power)
    groups = _integer(groups, 'groups')
    if len(p) % groups:
        raise ValueError('groups must divide angular grid')
    width = len(p)//groups
    return np.repeat(p.reshape(groups, width).sum(axis=1)/width, width)


def observation_error(reference, candidate, *, signal_floor=1e-12):
    a, b = _power(reference), _power(candidate)
    floor = _real(signal_floor, 'signal_floor')
    if a.shape != b.shape or floor <= 0:
        raise ValueError('equal shapes and positive signal_floor required')
    scale = max(float(np.linalg.norm(a)), floor)
    total = max(float(a.sum()), floor)
    return {'relative_l2': float(np.linalg.norm(b-a)/scale),
            'relative_l1': float(np.abs(b-a).sum()/total),
            'relative_power_error': float(abs(b.sum()-a.sum())/total),
            'max_absolute_error': float(np.max(np.abs(b-a)))}
