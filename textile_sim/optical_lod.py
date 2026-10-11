"""Auditable optical scale reduction and spectral observation, version 3.

The projected-area fit is an extinction *prior* of unoccluded cylindrical line
elements. It is not an opaque union, a measured extinction coefficient, or a
fabric BSDF. Its SGGX normal density and specular microflake phase function are
provided for mathematical validation, not substituted for the fiber shader.

Spectral integration consumes scalar radiance responses computed at declared
vacuum wavelengths. No RGB-channel interpolation stands in for wavelength data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import hashlib
import math
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import t as student_t

from .optical_scene import OpticalScene


CIE_SHA256 = "fa663e3535a7e0763a745993a1f0a192eb0275ac46ad2d1befd7626841e713c1"


def _array(value):
    a = np.asarray(value, dtype=float)
    if not np.isfinite(a).all():
        raise ValueError("nonfinite data")
    return a


def _frozen(a):
    return np.frombuffer(np.ascontiguousarray(a, dtype=float).tobytes(), dtype=float).reshape(a.shape)


def _directions(value):
    d = _array(value)
    if d.ndim != 2 or d.shape[1] != 3 or len(d) == 0:
        raise ValueError("directions require nonempty (N, 3)")
    n = np.linalg.norm(d, axis=1)
    if np.any(n == 0):
        raise ValueError("zero direction")
    return d / n[:, None]


def _positive(value, name):
    x = float(value)
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be positive finite")
    return x


def sphere_quadrature(n_mu=64, n_phi=128):
    """Gauss-Legendre in cos(theta), uniform azimuth; weights in steradians."""
    if any(isinstance(n, bool) or int(n) != n or n < 2 for n in (n_mu, n_phi)):
        raise ValueError("quadrature sizes must be integers >= 2")
    n_mu,n_phi=int(n_mu),int(n_phi)
    mu, w = np.polynomial.legendre.leggauss(int(n_mu))
    phi = (np.arange(int(n_phi)) + .5) * (2 * np.pi / n_phi)
    m, p = np.meshgrid(mu, phi, indexing="ij")
    s = np.sqrt(1 - m*m)
    d = np.stack((s*np.cos(p), s*np.sin(p), m), axis=-1).reshape(-1, 3)
    return d, np.repeat(w, n_phi) * (2*np.pi/n_phi)


def fibonacci_directions(count, offset=.5):
    """Deterministic equal-weight fitting directions, not an integration proof."""
    if isinstance(count, bool) or int(count) != count or count < 6:
        raise ValueError("direction count must be an integer >= 6")
    if not 0 < offset < 1:
        raise ValueError("offset must be inside (0, 1)")
    i = np.arange(int(count))
    z = 1 - 2*(i+offset)/count
    a = i*np.pi*(3-np.sqrt(5))
    return np.column_stack((np.sqrt(1-z*z)*np.cos(a), np.sqrt(1-z*z)*np.sin(a), z))


def projected_area_density(scene: OpticalScene, directions, volume_mm3, *, group_by="all"):
    """Return groupwise sum 2*r*L*sin(theta)/V in inverse millimeters.

    The caller supplies one explicit averaging volume for every group. This
    preserves additivity across levels. Cylindrical endcaps, joints, shadowing,
    coherence and spatial correlations are excluded. OpticalScene polylines only.
    """
    if not isinstance(scene, OpticalScene):
        raise ValueError("OpticalScene required")
    volume = _positive(volume_mm3, "volume_mm3")
    d = _directions(directions)
    if group_by not in ("all", "family", "yarn", "ply", "material"):
        raise ValueError("unknown hierarchy grouping")
    out = defaultdict(lambda: np.zeros(len(d)))
    for f in scene.fibers:
        if f.curve_basis != "polyline" or f.cross_section != "circle":
            raise ValueError("circular line-element geometry required")
        delta = np.diff(f.points_mm, axis=0)
        length = np.linalg.norm(delta, axis=1)
        tangent = delta/length[:, None]
        key = "all" if group_by == "all" else getattr(f, group_by if group_by == "family" else group_by+"_id")
        # A chunk prevents quadratic intermediate storage for large optical scenes.
        for start in range(0, len(d), 128):
            cosine = tangent @ d[start:start+128].T
            out[key][start:start+128] += ((2*f.radius_mm*length)[:, None] *
                np.sqrt(np.maximum(0, 1-cosine*cosine))).sum(axis=0)/volume
    return dict(out)


@dataclass(frozen=True, eq=False)
class SGGXProjection:
    """SPD S in mm^-2 when fitting mm^-1 directional area density.

    D(m) is an area-weighted normal density, NOT a unit-integral orientation PDF.
    Its visible projected normalization is integral (wi.m)+ D(m) dm = sigma(wi).
    """
    matrix: np.ndarray
    target_units: str = "mm^-1"
    status: str = "unoccluded_cylinder_projected_area_fit_only"

    def __post_init__(self):
        s = _array(self.matrix)
        if s.shape != (3, 3) or not np.allclose(s, s.T, rtol=0, atol=1e-12):
            raise ValueError("symmetric 3x3 S required")
        if np.linalg.eigvalsh(s).min() <= 0:
            raise ValueError("positive definite S required; singular fiber limit must be explicit")
        if self.target_units != "mm^-1":
            raise ValueError("explicit inverse-mm projected density contract required")
        object.__setattr__(self, "matrix", _frozen(s))

    def projected_area(self, directions):
        d = _directions(directions)
        return np.sqrt(np.einsum("ni,ij,nj->n", d, self.matrix, d))

    def normal_density(self, normals):
        m = _directions(normals)
        inv = np.linalg.inv(self.matrix)
        q = np.einsum("ni,ij,nj->n", m, inv, m)
        return 1 / (np.pi*np.sqrt(np.linalg.det(self.matrix))*q*q)

    def visible_normal_density(self, wi, normals):
        i = _directions(np.asarray(wi)[None])[0]
        m = _directions(normals)
        return np.maximum(m@i, 0)*self.normal_density(m)/self.projected_area(i[None])[0]

    def specular_phase(self, wi, wo):
        """Unit-albedo ideal reflective microflakes, both directions outward.

        This phase is not the dielectric-fiber hair BCSDF. Reversal reciprocity is
        sigma(wi)*p(wo|wi) = sigma(wo)*p(wi|wo), not p(wo|wi)=p(wi|wo).
        The exactly antipodal half-vector is undefined on a zero-measure set and
        is assigned zero solely for numerical integration.
        """
        i = _directions(np.asarray(wi)[None])[0]
        o = _directions(wo)
        h = i+o
        norm = np.linalg.norm(h, axis=1)
        active = norm > 1e-14
        result = np.zeros(len(o))
        result[active] = self.normal_density(h[active]/norm[active, None])/(4*self.projected_area(i[None])[0])
        return result


def fit_sggx_projected_area(directions, target, weights=None, *, relative_floor=1e-5):
    """Fit sigma, not a tangent covariance, by bounded log-Cholesky least squares.

    Returns (SGGXProjection, diagnostics). A declared SPD regularization limits
    the singular aligned-fiber approximation; the residual is never hidden.
    """
    d = _directions(directions)
    y = _array(target)
    if y.shape != (len(d),) or np.any(y < 0) or y.max() <= 0:
        raise ValueError("positive nontrivial projected-density target required")
    floor = _positive(relative_floor, "relative_floor")
    if floor >= .1:
        raise ValueError("relative floor must be below 0.1")
    w = np.ones(len(d)) if weights is None else _array(weights)
    if w.shape != y.shape or np.any(w <= 0):
        raise ValueError("positive fitting weights required")
    w = w / w.sum()
    scale = np.sqrt(np.sum(w*y*y))
    yn = y/scale
    a = np.column_stack((d[:,0]**2,d[:,1]**2,d[:,2]**2,2*d[:,0]*d[:,1],2*d[:,0]*d[:,2],2*d[:,1]*d[:,2]))
    singular = np.linalg.svd(a*np.sqrt(w[:,None]),compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0]*1e-10))
    if rank < 6:
        raise ValueError("angular observations do not identify all six symmetric S entries")
    s0 = np.linalg.lstsq(a*np.sqrt(w[:,None]), yn*yn*np.sqrt(w), rcond=None)[0]
    s0 = np.array([[s0[0],s0[3],s0[4]],[s0[3],s0[1],s0[5]],[s0[4],s0[5],s0[2]]])
    eig, vec = np.linalg.eigh(s0)
    s0 = (vec*np.maximum(eig, floor**2*10))@vec.T
    chol = np.linalg.cholesky(s0)
    x0 = [np.log(chol[0,0]),np.log(chol[1,1]),np.log(chol[2,2]),chol[1,0],chol[2,0],chol[2,1]]
    def matrix(x):
        l = np.array([[np.exp(x[0]),0.,0.],[x[3],np.exp(x[1]),0.],[x[4],x[5],np.exp(x[2])]])
        return l@l.T + floor**2*np.eye(3)
    def residual(x):
        return (np.sqrt(np.einsum("ni,ij,nj->n",d,matrix(x),d))-yn)*np.sqrt(w)
    sol = least_squares(residual,x0,bounds=([-20]*3+[-10]*3,[5]*3+[10]*3),
                        ftol=1e-11,xtol=1e-11,gtol=1e-11,max_nfev=3000)
    if not sol.success:
        raise RuntimeError("SGGX projected-area fit did not converge")
    fit = SGGXProjection(matrix(sol.x)*scale*scale)
    pred = fit.projected_area(d)
    diag = {"objective":"weighted squared error in directional projected area density",
            "training_count":len(y),"training_relative_rmse":float(np.sqrt(np.sum(w*(pred-y)**2))/scale),
            "quadratic_design_rank":rank,"quadratic_design_condition_number":float(singular[0]/singular[-1]),
            "training_max_error_over_rms_target":float(np.max(np.abs(pred-y))/scale),
            "regularization_floor_relative_to_target_rms":floor,
            "matrix_units":"mm^-2", "optimizer_nfev":int(sol.nfev),
            "fit_success":bool(sol.success),"target_rms_per_mm":float(scale),
            "smallest_eigenvalue_per_mm2":float(np.linalg.eigvalsh(fit.matrix).min()),
            "not_estimated":["spatial correlations","shadowing","single-scattering albedo","fiber BCSDF","fabric BSDF"]}
    return fit, diag


def trapezoid_weights(x):
    x = _array(x)
    if x.ndim != 1 or len(x) < 2 or np.any(np.diff(x) <= 0):
        raise ValueError("strictly increasing 1D quadrature grid required")
    dx = np.diff(x)
    return np.r_[dx[0]/2, (dx[:-1]+dx[1:])/2, dx[-1]/2]


def load_cie1931(path=None):
    """Read the original CIE 2019 1-nm CSV, with mandatory published SHA-256."""
    if path is None:
        path = Path(__file__).resolve().parents[1]/"data/optical_v3/cie/CIE_xyz_1931_2deg.csv"
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CIE_SHA256:
        raise ValueError("CIE source checksum mismatch")
    table = np.loadtxt(path, delimiter=",")
    if table.shape != (471,4) or not np.array_equal(table[:,0],np.arange(360,831)):
        raise ValueError("unexpected CIE sampling domain")
    return table[:,0], table[:,1:]


def planck_relative(wavelength_nm, temperature_kelvin):
    """Relative spectral radiance per wavelength, using SI h,c,k constants.

    The multiplicative radiometric scale is deliberately normalized to max=1;
    it is not D65, a measured lamp SPD, or an absolute calibrated light output.
    """
    l = _array(wavelength_nm)*1e-9
    t = _positive(temperature_kelvin,"temperature_kelvin")
    if np.any(l <= 0):
        raise ValueError("positive vacuum wavelengths required")
    q = .014387768775039337/(l*t)
    # log(expm1(q)) = q + log(1-exp(-q)) avoids low-temperature overflow.
    logb = -5*np.log(l) - q - np.log(-np.expm1(-q))
    return np.exp(logb-logb.max())


def spectral_xyz_weights(sample_wavelength_nm, observer_nm, observer_xyz, source_spd):
    """Map radiance samples to XYZ using piecewise-linear radiance interpolation.

    Source and CMFs live on the dense observer grid. Only the declared sampled
    wavelength interval is integrated; no extrapolation. White is normalized to
    Y=1 under the same source and interval. This is a truncated-range colorimetric
    observation, not an absolute luminance measurement or camera calibration.
    """
    l, o = _array(sample_wavelength_nm), _array(observer_nm)
    trapezoid_weights(l); trapezoid_weights(o)
    cmf, spd = _array(observer_xyz), _array(source_spd)
    if cmf.shape != (len(o),3) or spd.shape != (len(o),) or np.any(cmf<0) or np.any(spd<0):
        raise ValueError("nonnegative observer and source samples required")
    if l[0] < o[0] or l[-1] > o[-1]:
        raise ValueError("observer support must enclose all rendered wavelengths")
    q = np.unique(np.r_[l, o[(o>l[0])&(o<l[-1])]])
    c = np.column_stack([np.interp(q,o,cmf[:,j]) for j in range(3)])
    e = np.interp(q,o,spd)
    w = trapezoid_weights(q)
    norm = np.sum(w*e*c[:,1])
    if norm <= 0:
        raise ValueError("source has zero photopic normalization")
    j = np.clip(np.searchsorted(l,q,side="right")-1,0,len(l)-2)
    u = (q-l[j])/(l[j+1]-l[j])
    weights = np.zeros((len(l),3))
    for k in range(3):
        np.add.at(weights[:,k],j,w*e*c[:,k]*(1-u)/norm)
        np.add.at(weights[:,k],j+1,w*e*c[:,k]*u/norm)
    full_norm = float(np.sum(trapezoid_weights(o)*spd*cmf[:,1]))
    return weights, {"sample_wavelength_range_nm":[float(l[0]),float(l[-1])],
        "sample_count":len(l),"integration_grid_count":len(q),
        "normalization":"Y of unit radiance response = 1 over the sampled wavelength interval",
        "observer_reference":"CIE 1931 2 degree, DOI 10.25039/CIE.DS.xvudnb9b",
        "source_photopic_mass_outside_interval":float(max(0,1-norm/full_norm)),
        "radiance_interpolation":"piecewise linear between computed wavelength samples",
        "white_xyz":weights.sum(axis=0).tolist()}


def integrate_xyz(radiance, weights):
    r, w = _array(radiance), _array(weights)
    if w.ndim != 2 or w.shape[1] != 3 or r.shape[-1] != len(w) or np.any(r<0):
        raise ValueError("radiance last axis must match positive spectral weights")
    if np.any(w<0):
        raise ValueError("nonnegative spectral weights required")
    return np.einsum("...l,lc->...c", r, w)


def xyz_to_linear_srgb(xyz):
    """D65-referenced linear sRGB primaries, without chromatic adaptation/clipping."""
    x = _array(xyz)
    if x.shape[-1] != 3:
        raise ValueError("XYZ last axis must have length 3")
    matrix = np.array([[3.2404542,-1.5371385,-.4985314],[-.9692660,1.8760108,.0415560],[.0556434,-.2040259,1.0572252]])
    return x@matrix.T


def paired_mean_interval(before, after, confidence=.95):
    """Student-t CI over independent paired seed replicates, not over pixels.

    The result quantifies Monte Carlo repeatability conditional on the simulator.
    It excludes model error, material uncertainty and experimental variability.
    """
    a,b = _array(before),_array(after)
    if a.shape != b.shape or a.ndim < 1 or len(a)<2:
        raise ValueError("at least two aligned independent seed replicates required")
    if not 0<confidence<1:
        raise ValueError("confidence must be inside (0,1)")
    delta = b-a
    mean = delta.mean(axis=0)
    se = delta.std(axis=0,ddof=1)/np.sqrt(len(delta))
    half = float(student_t.ppf((1+confidence)/2,len(delta)-1))*se
    return {"paired_count":len(delta),"confidence":confidence,
            "mean_delta":mean.tolist(),"standard_error":se.tolist(),
            "interval_low":(mean-half).tolist(),"interval_high":(mean+half).tolist(),
            "scope":"Monte Carlo repeatability only; Student-t finite-replicate approximation"}
