"""Reduced, convex yarn-height equilibrium for a finite orthogonal weave.

This is a fixed-track, small-slope beam model, not a full discrete elastic rod,
contact/friction solver, or fabric drape simulator.  Each yarn has fixed projected
coordinates and endpoint heights; only its height samples are unknown.  Exact
segment extension is combined with explicitly small-slope Euler--Bernoulli
bending.  Conservative linear crossing/slope constraints keep yarn envelopes
separated.  See notes/weave_mechanics_v3.md for the bound and assumptions.

Units: mm, N, N*mm.  All stiffnesses in supplied examples are synthetic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import numbers
from typing import Any

import numpy as np
from scipy import linalg, optimize, sparse

from .hierarchy import HierarchyGeometry, YarnSpec, build_yarn
from .weave_draft import WeaveDraft

SCHEMA_VERSION = "textile.reduced_weave_mechanics/3.0"


def _real(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a real scalar")
    value = float(value)
    if not np.isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError(f"invalid {name}")
    return value


def _int(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _immutable(values):
    arr = np.ascontiguousarray(values, dtype=np.float64)
    return np.frombuffer(arr.tobytes(), dtype=np.float64).reshape(arr.shape)


@dataclass(frozen=True)
class YarnElasticity:
    """Independent effective yarn stiffnesses; neither is inferred from optics.

    ``rest_fraction`` multiplies every projected segment length.  Values <=1
    ensure every allowed segment is in tension or unstretched, making its axial
    energy convex in height difference.  Compressive/buckling inputs are rejected.
    """
    axial_stiffness_N: float = .02
    bending_stiffness_N_mm2: float = 2.e-6
    rest_fraction: float = .995
    source: str = "synthetic reduced-mechanics verification fixture"
    data_status: str = "synthetic"

    def __post_init__(self):
        for name in ("axial_stiffness_N", "bending_stiffness_N_mm2"):
            object.__setattr__(self, name, _real(getattr(self, name), name, nonnegative=True))
        if self.axial_stiffness_N == self.bending_stiffness_N_mm2 == 0:
            raise ValueError("at least one stiffness must be positive")
        r = _real(self.rest_fraction, "rest_fraction", positive=True)
        if r > 1:
            raise ValueError("rest_fraction > 1 would allow compression/buckling outside this convex model")
        object.__setattr__(self, "rest_fraction", r)
        if self.data_status not in ("synthetic", "measured", "literature") or not self.source.strip():
            raise ValueError("stiffness source and data_status are required")


@dataclass(frozen=True)
class ReducedWeaveSpec:
    draft: WeaveDraft
    warp_envelope_radius_mm: float
    weft_envelope_radius_mm: float
    warp_elasticity: YarnElasticity = field(default_factory=YarnElasticity)
    weft_elasticity: YarnElasticity = field(default_factory=YarnElasticity)
    warp_count: int = 3
    weft_count: int = 3
    warp_pitch_mm: float = .24
    weft_pitch_mm: float = .24
    clearance_mm: float = .004
    max_slope: float = .30
    segments_per_crossing: int = 8
    padding_crossings: int = 1
    initial_warp_share: float = .5
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION or not isinstance(self.draft, WeaveDraft):
            raise ValueError("supported mechanics schema and WeaveDraft required")
        for name in ("warp_elasticity", "weft_elasticity"):
            if not isinstance(getattr(self, name), YarnElasticity):
                raise ValueError(f"{name} must be YarnElasticity")
        for name in ("warp_count", "weft_count", "padding_crossings"):
            object.__setattr__(self, name, _int(getattr(self, name), name))
        object.__setattr__(self, "segments_per_crossing",
                           _int(self.segments_per_crossing, "segments_per_crossing", 2))
        for name in ("warp_envelope_radius_mm", "weft_envelope_radius_mm", "warp_pitch_mm",
                     "weft_pitch_mm", "max_slope"):
            object.__setattr__(self, name, _real(getattr(self, name), name, positive=True))
        object.__setattr__(self, "clearance_mm", _real(self.clearance_mm, "clearance_mm", nonnegative=True))
        share = _real(self.initial_warp_share, "initial_warp_share")
        if not 0 <= share <= 1:
            raise ValueError("initial_warp_share must be in [0,1]")
        if self.max_slope > .5:
            raise ValueError("max_slope > 0.5 exceeds this small-slope model's declared domain")
        for family in ("warp", "weft"):
            if getattr(self, family+"_pitch_mm") < 2*getattr(self, family+"_envelope_radius_mm")+self.clearance_mm:
                raise ValueError(f"parallel {family} envelopes cannot meet clearance")

    @property
    def crossing_separation_mm(self):
        return (self.warp_envelope_radius_mm+self.weft_envelope_radius_mm+self.clearance_mm)*np.sqrt(1+2*self.max_slope**2)

    def to_dict(self):
        value = asdict(self)
        value["draft"] = self.draft.to_dict()
        value["units"] = {"length": "mm", "force": "N", "energy": "N*mm"}
        return value

    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        if value.pop("units", {"length": "mm", "force": "N", "energy": "N*mm"}) != {
                "length": "mm", "force": "N", "energy": "N*mm"}:
            raise ValueError("unsupported mechanics units")
        value["draft"] = WeaveDraft.from_dict(value["draft"])
        for key in ("warp_elasticity", "weft_elasticity"):
            if key in value:
                value[key] = YarnElasticity(**value[key])
        return cls(**value)


@dataclass(frozen=True)
class _Track:
    family: str
    index: int
    projected_mm: np.ndarray
    transverse_mm: float
    variable_slice: slice
    elasticity: YarnElasticity
    d1: Any
    d2: Any

    @property
    def h(self):
        return float(self.projected_mm[1]-self.projected_mm[0])


def beam_energy_gradient_hessian(z_mm, h_mm, elasticity: YarnElasticity):
    """One uniform-grid beam, with both endpoint heights fixed at zero.

    Input contains interior heights only.  Returns excess energy above the flat
    pretensioned state, its exact gradient, and Hessian.  A positive rest_fraction
    <=1 gives a PSD extension Hessian.  Bending is B/2*integral(z''**2 dx), not the
    rotation-invariant elastica curvature energy.  This helper also admits axial
    stiffness zero for an independent linear-beam benchmark.
    """
    z = np.asarray(z_mm, dtype=float)
    h = _real(h_mm, "h_mm", positive=True)
    if z.ndim != 1 or len(z) < 1 or not np.all(np.isfinite(z)):
        raise ValueError("finite interior beam heights required")
    if not isinstance(elasticity, YarnElasticity):
        raise TypeError("elasticity must be YarnElasticity")
    n = len(z)
    d1 = sparse.diags((-np.ones(n), np.ones(n)), (-1, 0), shape=(n+1, n), format="csr")
    d2 = sparse.diags((np.ones(n-1), -2*np.ones(n), np.ones(n-1)), (-1, 0, 1), shape=(n, n), format="csr")
    return _beam_egh(z, h, elasticity, d1, d2)


def _beam_egh(z, h, material, d1, d2):
    dz = d1@z
    length = np.sqrt(h*h+dz*dz)
    rest = material.rest_fraction*h
    ea, bend = material.axial_stiffness_N, material.bending_stiffness_N_mm2
    # Algebraically equivalent subtraction, without subtracting two large
    # pretension energies when heights are close to zero.
    excess_length = dz*dz/(length+h)
    stretch = ea/(2*rest)*np.sum(excess_length*(length+h-2*rest))
    second = d2@z
    bending = bend/(2*h**3)*np.dot(second, second)
    grad = d1.T@(ea/rest*(1-rest/length)*dz)+bend/h**3*(d2.T@second)
    axial_hessian = ea/rest*(1-rest*h*h/length**3)
    hess = d1.T@sparse.diags(axial_hessian)@d1+bend/h**3*(d2.T@d2)
    return float(stretch+bending), np.asarray(grad), hess.toarray()


class ReducedWeaveProblem:
    """Finite two-family weave with zero-height pinned ends one or more pitches out.

    The continuum boundary interpretation is simply supported: endpoint heights
    prescribed, rotations free, no imposed end moment.  At finite mesh the
    discrete bending energy defines the boundary approximation explicitly.
    """
    def __init__(self, spec: ReducedWeaveSpec):
        if not isinstance(spec, ReducedWeaveSpec):
            raise TypeError("spec must be ReducedWeaveSpec")
        self.spec = spec
        self.tracks = []
        offset = 0
        for family in ("warp", "weft"):
            warp = family == "warp"
            count = spec.warp_count if warp else spec.weft_count
            cross_count = spec.weft_count if warp else spec.warp_count
            pitch = spec.weft_pitch_mm if warp else spec.warp_pitch_mm
            transverse_pitch = spec.warp_pitch_mm if warp else spec.weft_pitch_mm
            intervals = (cross_count-1+2*spec.padding_crossings)*spec.segments_per_crossing
            projected = np.linspace(-spec.padding_crossings*pitch,
                (cross_count-1+spec.padding_crossings)*pitch, intervals+1)-.5*(cross_count-1)*pitch
            n = intervals-1
            d1 = sparse.diags((-np.ones(n), np.ones(n)), (-1, 0), shape=(n+1, n), format="csr")
            d2 = sparse.diags((np.ones(n-1), -2*np.ones(n), np.ones(n-1)), (-1, 0, 1), format="csr")
            for index in range(count):
                self.tracks.append(_Track(family, index, _immutable(projected),
                    (index-.5*(count-1))*transverse_pitch, slice(offset, offset+n),
                    getattr(spec, family+"_elasticity"), d1, d2))
                offset += n
        self.tracks = tuple(self.tracks)
        self.dimension = offset
        # Constraints have uniform length units: A z >= b.  They include
        # crossings first, then positive/negative step-height slope limits.
        rows, lower, names = [], [], []
        for i in range(spec.weft_count):
            for j in range(spec.warp_count):
                w, f = self.tracks[j], self.tracks[spec.warp_count+i]
                wi = (spec.padding_crossings+i)*spec.segments_per_crossing-1+w.variable_slice.start
                fi = (spec.padding_crossings+j)*spec.segments_per_crossing-1+f.variable_slice.start
                sign = 1 if spec.draft.crossing(j, i) else -1
                row = np.zeros(offset)
                row[wi], row[fi] = sign, -sign
                rows.append(row); lower.append(spec.crossing_separation_mm)
                names.append(f"crossing:weft={i}:warp={j}")
        self.crossing_count = len(rows)
        for tr in self.tracks:
            for direction in (1, -1):
                for k, local in enumerate(tr.d1.toarray()):
                    row = np.zeros(offset)
                    row[tr.variable_slice] = direction*local
                    rows.append(row); lower.append(-spec.max_slope*tr.h)
                    names.append(f"slope:{tr.family}:{tr.index}:{k}:{direction:+d}")
        self.constraint_matrix = _immutable(rows)
        self.constraint_lower_mm = _immutable(lower)
        self.constraint_names = tuple(names)
        self.length_scale_mm = .5*(spec.warp_pitch_mm+spec.weft_pitch_mm)
        # Depend only on physics, not starting geometry or solver tolerance.
        self.energy_scale_N_mm = sum(
            tr.elasticity.bending_stiffness_N_mm2/(tr.projected_mm[-1]-tr.projected_mm[0])+
            tr.elasticity.axial_stiffness_N*(tr.projected_mm[-1]-tr.projected_mm[0])
            for tr in self.tracks)

    def _vector(self, values):
        arr = np.asarray(values, dtype=float)
        if arr.shape != (self.dimension,) or not np.all(np.isfinite(arr)):
            raise ValueError("finite height vector with problem.dimension entries required")
        return arr

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.spec.to_dict(), sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()

    def state_sha256(self, z_mm):
        return hashlib.sha256(np.asarray(self._vector(z_mm), dtype="<f8").tobytes()).hexdigest()

    def initial_heights(self):
        """Feasible C2 kinematic crimp with prescribed family share, if possible."""
        z = np.zeros(self.dimension)
        s = self.spec
        for tr in self.tracks:
            warp = tr.family == "warp"
            cross_count = s.weft_count if warp else s.warp_count
            pitch = s.weft_pitch_mm if warp else s.warp_pitch_mm
            crossing_knots = (np.arange(cross_count)-.5*(cross_count-1))*pitch
            knots = np.r_[tr.projected_mm[0], crossing_knots, tr.projected_mm[-1]]
            sign = np.array([1 if s.draft.crossing(tr.index, k) else -1 for k in range(cross_count)]) if warp else np.array([-1 if s.draft.crossing(k, tr.index) else 1 for k in range(cross_count)])
            heights = np.r_[0., sign*s.crossing_separation_mm*(s.initial_warp_share if warp else 1-s.initial_warp_share), 0.]
            q = tr.projected_mm[1:-1]
            idx = np.clip(np.searchsorted(knots, q, side="right")-1, 0, len(knots)-2)
            u = (q-knots[idx])/(knots[idx+1]-knots[idx])
            blend = 10*u**3-15*u**4+6*u**5
            z[tr.variable_slice] = heights[idx]+(heights[idx+1]-heights[idx])*blend
        diag = self.constraint_diagnostics(z)
        if diag["max_violation_mm"] > 1e-12*self.length_scale_mm:
            raise ValueError("C2 initialization violates slope/clearance constraints; increase pitch, reduce envelope or change share")
        return z

    def energy_gradient_hessian(self, z_mm):
        z = self._vector(z_mm)
        energy = 0.
        gradient = np.zeros(self.dimension)
        hessian = np.zeros((self.dimension, self.dimension))
        for tr in self.tracks:
            e, g, h = _beam_egh(z[tr.variable_slice], tr.h, tr.elasticity, tr.d1, tr.d2)
            energy += e; gradient[tr.variable_slice] = g
            hessian[tr.variable_slice, tr.variable_slice] = h
        return float(energy), gradient, hessian

    def constraint_diagnostics(self, z_mm):
        z = self._vector(z_mm)
        slack = self.constraint_matrix@z-self.constraint_lower_mm
        slopes = [np.max(np.abs(tr.d1@z[tr.variable_slice]/tr.h)) for tr in self.tracks]
        family_slopes = {family: max(value for tr, value in zip(self.tracks, slopes) if tr.family == family)
                         for family in ("warp", "weft")}
        configured_bound_valid = max(slopes) <= self.spec.max_slope+1e-12
        d = self.spec.warp_envelope_radius_mm+self.spec.weft_envelope_radius_mm
        min_cross = float(np.min(slack[:self.crossing_count]+self.spec.crossing_separation_mm))
        same_family = min(self.spec.warp_pitch_mm-2*self.spec.warp_envelope_radius_mm,
                          self.spec.weft_pitch_mm-2*self.spec.weft_envelope_radius_mm)
        return {"max_violation_mm": float(max(0., -np.min(slack))),
            "min_crossing_separation_mm": min_cross, "max_abs_slope": float(max(slopes)),
            "configured_slope_bound": self.spec.max_slope,
            "configured_slope_bound_satisfied": bool(configured_bound_valid),
            "conservative_orthogonal_envelope_clearance_mm": float(min_cross/np.sqrt(1+2*self.spec.max_slope**2)-d) if configured_bound_valid else None,
            "observed_slope_orthogonal_envelope_clearance_bound_mm": float(min_cross/np.sqrt(1+sum(value*value for value in family_slopes.values()))-d),
            "family_max_abs_slope": {key: float(value) for key, value in family_slopes.items()},
            "parallel_family_clearance_bound_mm": float(same_family),
            "small_slope_bending_integrand_overestimate_bound": float((1+max(slopes)**2)**2.5-1),
            "small_slope_diagnostic_scope": "continuum graph integrand factor at observed edge slopes; not a discrete-curvature or real-material error certificate",
            "bound_scope": "piecewise-linear yarn centerlines and specified circular envelopes; no same-yarn fiber contact certificate"}

    def centerlines(self, z_mm):
        z = self._vector(z_mm)
        result = {}
        for tr in self.tracks:
            height = np.r_[0., z[tr.variable_slice], 0.]
            fixed = np.full(len(height), tr.transverse_mm)
            points = np.column_stack((fixed, tr.projected_mm, height)) if tr.family == "warp" else np.column_stack((tr.projected_mm, fixed, height))
            result[(tr.family, tr.index)] = points
        return result

    def summary(self, z_mm):
        z = self._vector(z_mm)
        families = {}
        for family in ("warp", "weft"):
            second_moment = np.zeros((3, 3)); length = 0.; projected = 0.; tension = []; heights = []
            for tr in self.tracks:
                if tr.family != family:
                    continue
                dz = tr.d1@z[tr.variable_slice]
                ell = np.sqrt(tr.h**2+dz**2)
                vec = np.column_stack((np.zeros(len(dz)), np.full(len(dz), tr.h), dz)) if family == "warp" else np.column_stack((np.full(len(dz), tr.h), np.zeros(len(dz)), dz))
                t = vec/ell[:, None]
                second_moment += np.einsum("n,ni,nj->ij", ell, t, t)
                length += float(sum(ell)); projected += len(ell)*tr.h
                tension.extend(tr.elasticity.axial_stiffness_N*(ell/(tr.elasticity.rest_fraction*tr.h)-1))
                heights.extend(z[tr.variable_slice])
            families[family] = {"centerline_length_mm": length, "projected_length_mm": projected,
                "crimp_ratio": length/projected-1, "height_rms_mm": float(np.sqrt(np.mean(np.square(heights)))),
                "tangent_second_moment": (second_moment/length).tolist(),
                "axial_force_min_N": float(min(tension)), "axial_force_max_N": float(max(tension))}
        return {"energy_excess_N_mm": self.energy_gradient_hessian(z)[0],
            "constraints": self.constraint_diagnostics(z), "families": families}


@dataclass(frozen=True)
class WeaveEquilibrium:
    initial_heights_mm: np.ndarray
    heights_mm: np.ndarray
    diagnostics: dict
    history: tuple[dict, ...]
    problem_sha256: str
    height_state_sha256: str
    stationarity_tolerance: float = 1e-8
    feasibility_tolerance: float = 1e-9


def equilibrium_residual(problem: ReducedWeaveProblem, z_mm, *, active_tolerance_mm=None):
    """Independent KKT check, using NNLS nonnegative active multipliers.

    Gradient units are N.  Constraint rows are dimensionless and multipliers
    have N units.  The denominator is a physics-derived force scale independent
    of common stiffness rescaling.  Residuals are reported, not replaced with
    optimizer.success.  Inactive multipliers are fixed to zero.
    """
    z = problem._vector(z_mm)
    _, gradient, _ = problem.energy_gradient_hessian(z)
    tolerance = 1e-8*problem.length_scale_mm if active_tolerance_mm is None else _real(active_tolerance_mm, "active_tolerance_mm", positive=True)
    slack = problem.constraint_matrix@z-problem.constraint_lower_mm
    active = np.flatnonzero(slack <= tolerance)
    force_scale = problem.energy_scale_N_mm/problem.length_scale_mm
    multipliers = np.zeros(len(slack))
    if len(active):
        # Normalize the right hand side, so NNLS termination is invariant under
        # common multiplication of all stiffnesses by a positive constant.
        value, _ = optimize.nnls(problem.constraint_matrix[active].T, gradient/force_scale,
                                 maxiter=max(1000, 10*len(active)))
        multipliers[active] = value*force_scale
    residual = gradient-problem.constraint_matrix.T@multipliers
    return {"stationarity_inf_N": float(np.max(np.abs(residual))),
        "stationarity_relative": float(np.max(np.abs(residual))/force_scale),
        "stationarity_relative_to_gradient": float(np.max(np.abs(residual))/max(np.max(np.abs(gradient)), force_scale*1e-15)),
        "complementarity_N_mm": float(np.max(np.abs(slack*multipliers))),
        "complementarity_relative": float(np.max(np.abs(slack*multipliers))/problem.energy_scale_N_mm),
        "max_constraint_violation_mm": float(max(0., -slack.min())),
        "active_constraint_count": int(len(active)),
        "active_tolerance_mm": tolerance, "multipliers_N": multipliers.tolist(),
        "multiplier_scope": "ideal reduced-model inequality reactions, not measured pressure or friction"}


def solve_equilibrium(problem: ReducedWeaveProblem, initial_heights_mm=None, *,
                      max_iterations=500, stationarity_tolerance=1e-8, feasibility_tolerance=1e-9):
    """Minimize the convex energy and independently certify its numerical KKT state.

    The linear change of variables uses the initial-state bending/extension Hessian
    as a preconditioner.  It changes conditioning, not the physical objective.
    SLSQP solves the remaining nonlinear extension and linear inequalities.
    Failure to satisfy the independent residual/feasibility gates raises.
    """
    if not isinstance(problem, ReducedWeaveProblem):
        raise TypeError("problem must be ReducedWeaveProblem")
    max_iterations = _int(max_iterations, "max_iterations")
    st = _real(stationarity_tolerance, "stationarity_tolerance", positive=True)
    ft = _real(feasibility_tolerance, "feasibility_tolerance", positive=True)
    z0 = problem.initial_heights() if initial_heights_mm is None else problem._vector(initial_heights_mm).copy()
    if problem.constraint_diagnostics(z0)["max_violation_mm"] > ft*problem.length_scale_mm:
        raise ValueError("initial point must be feasible")
    length, scale = problem.length_scale_mm, problem.energy_scale_N_mm
    # Full-rank Cholesky on the initial Hessian.  For a zero bending/zero initial
    # tension mode use identity scaling; no regularization enters the energy.
    h0 = problem.energy_gradient_hessian(z0)[2]*length**2/scale
    try:
        factor = linalg.cholesky(h0, lower=True)
        transform = linalg.solve_triangular(factor.T, np.eye(problem.dimension), lower=False)
    except linalg.LinAlgError:
        transform = np.eye(problem.dimension)
    inverse = linalg.solve(transform, z0/length)
    a = problem.constraint_matrix@transform
    lower = problem.constraint_lower_mm/length
    history = []

    def objective(q):
        z = length*(transform@q)
        energy, gradient, _ = problem.energy_gradient_hessian(z)
        return energy/scale, (length/scale)*(transform.T@gradient)

    def callback(q):
        z = length*(transform@q)
        history.append({"iteration": len(history)+1,
                        "energy_excess_N_mm": problem.energy_gradient_hessian(z)[0],
                        "max_constraint_violation_mm": problem.constraint_diagnostics(z)["max_violation_mm"]})

    result = optimize.minimize(objective, inverse, method="SLSQP", jac=True,
        constraints=[optimize.LinearConstraint(a, lower, np.inf)], callback=callback,
        options={"maxiter": max_iterations, "ftol": min(1e-13, st**2), "disp": False})
    z = length*(transform@result.x)
    residual = equilibrium_residual(problem, z)
    e0 = problem.energy_gradient_hessian(z0)[0]
    e1 = problem.energy_gradient_hessian(z)[0]
    certified = (residual["stationarity_relative"] <= st and
                 residual["complementarity_relative"] <= 10*st and
                 residual["max_constraint_violation_mm"] <= ft*length and
                 e1 <= e0+1e-12*scale)
    diagnostics = {"schema_version": SCHEMA_VERSION, "solver": "SLSQP; analytic gradient; Hessian preconditioning",
        "solver_success": bool(result.success), "solver_message": str(result.message),
        "iterations": int(result.nit), "function_evaluations": int(result.nfev),
        "initial_energy_excess_N_mm": e0, "final_energy_excess_N_mm": e1,
        "energy_reduction_fraction": float(1-e1/e0) if e0 > 0 else 0.,
        "stationarity_tolerance": st, "feasibility_tolerance_relative_length": ft,
        "independent_kkt_certified": bool(certified), "kkt": residual,
        "initial": problem.summary(z0), "relaxed": problem.summary(z),
        "scope": "fixed-track, tension-domain axial energy plus small-slope bending; conservative envelope constraints; no friction/drape"}
    if not certified:
        raise RuntimeError("independent equilibrium gates failed: "+json.dumps({
            "solver_message": str(result.message), "kkt": residual, "energy": [e0, e1]}))
    diagnostics["problem_sha256"] = problem.sha256
    diagnostics["height_state_sha256"] = problem.state_sha256(z)
    return WeaveEquilibrium(_immutable(z0), _immutable(z), diagnostics, tuple(history),
                            problem.sha256, problem.state_sha256(z), st, ft)


def build_relaxed_hierarchy(problem: ReducedWeaveProblem, z_or_result, warp_yarn: YarnSpec,
                            weft_yarn: YarnSpec, *, subdivisions=4, seed=20261011):
    """Sweep v2 fiber/ply hierarchy on exact piecewise-linear mechanical tracks.

    Additional subdivisions sample the same polyline, not an unreported spline.
    Fiber twist uses actual relaxed parent arclength.  This is a geometric
    embedding; fiber material-point identity and fiber mass/strain are not solved.
    Global explicit-fiber clearance must be audited by the caller after sweep.
    """
    subdivisions = _int(subdivisions, "subdivisions")
    seed = _int(seed, "seed", 0)
    result = z_or_result if isinstance(z_or_result, WeaveEquilibrium) else None
    z = problem._vector(result.heights_mm if result else z_or_result)
    checked_kkt = None
    if result is not None:
        if result.problem_sha256 != problem.sha256:
            raise ValueError("equilibrium result belongs to a different mechanics problem")
        if result.height_state_sha256 != problem.state_sha256(z):
            raise ValueError("equilibrium height state hash does not match result")
        # Recompute, rather than trusting a mutable diagnostic dictionary or an
        # optimizer-success flag supplied with the state.
        checked_kkt = equilibrium_residual(problem, z)
        st = _real(result.stationarity_tolerance, "result.stationarity_tolerance", positive=True)
        ft = _real(result.feasibility_tolerance, "result.feasibility_tolerance", positive=True)
        if (checked_kkt["stationarity_relative"] > st or
            checked_kkt["complementarity_relative"] > 10*st or
            checked_kkt["max_constraint_violation_mm"] > ft*problem.length_scale_mm or
            problem.energy_gradient_hessian(z)[0] > problem.energy_gradient_hessian(result.initial_heights_mm)[0]+1e-12*problem.energy_scale_N_mm):
            raise ValueError("equilibrium result failed independently recomputed export gates")
    constraints = problem.constraint_diagnostics(z)
    if constraints["max_violation_mm"] > 1e-9*problem.length_scale_mm:
        raise ValueError("cannot export infeasible mechanical geometry")
    for family, yarn in (("warp", warp_yarn), ("weft", weft_yarn)):
        if not isinstance(yarn, YarnSpec):
            raise TypeError("warp_yarn and weft_yarn must be YarnSpec")
        if yarn.envelope_radius_mm > getattr(problem.spec, family+"_envelope_radius_mm")+1e-14:
            raise ValueError("explicit hierarchy exceeds declared mechanical yarn envelope")
    records, yarns, plies = [], {}, {}
    for (family, index), points in problem.centerlines(z).items():
        fraction = np.arange(subdivisions)/subdivisions
        fine = (points[:-1, None, :]+fraction[None, :, None]*(points[1:]-points[:-1])[:, None, :]).reshape(-1, 3)
        fine = np.vstack((fine, points[-1]))
        template = warp_yarn if family == "warp" else weft_yarn
        g = build_yarn(template, fine, family=family, yarn_index=index, seed=seed, initial_normal=(0, 0, 1))
        records.extend(g.fiber_records); yarns.update(g.yarns); plies.update(g.plies)
    state_hash = problem.state_sha256(z)
    return HierarchyGeometry(tuple(records), yarns, plies,
        {"kind": "reduced_mechanics_embedded_hierarchy", "mechanics": problem.spec.to_dict(),
         "warp_yarn": warp_yarn.to_dict(), "weft_yarn": weft_yarn.to_dict(),
         "subdivisions": subdivisions, "seed": seed, "height_state_sha256": state_hash},
        {"geometry_tileable": False, "centerline_basis": "mechanical_piecewise_linear",
         "physical_mechanics_solved": "reduced_yarn_height_equilibrium" if result else False,
         "equilibrium_status": "independently_kkt_certified" if result else "supplied_feasible_heights",
         "equilibrium_kkt": checked_kkt,
         "mechanics_problem_sha256": problem.sha256,
         "envelope_constraints": constraints,
         "fiber_material_points_conserved": False,
         "scope": "geometric microstructure embedding on reduced yarn mechanics; no constituent fiber mechanics or mass conservation"})
