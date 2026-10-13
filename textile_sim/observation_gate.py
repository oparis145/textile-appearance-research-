"""Acceptance gates in observation space, with explicit error and sampling scope.

A CI including zero is not evidence of equivalence. Independent repeats occupy
axis 0; pixels, wavelengths, channels, and duplicate runs are NOT extra repeats.
No test in this module certifies a numerical reference or measured-fabric model.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import t as student_t


def _matrix(x, name):
    a = np.asarray(x, dtype=float)
    if a.ndim != 2 or a.shape[0] < 3 or a.shape[1] < 1 or not np.isfinite(a).all():
        raise ValueError(f'{name} must be finite [independent_repeat, condition], at least 3 repeats')
    return a


def _vector(value, count, name, *, positive=False):
    v = np.asarray(value, dtype=float)
    try:
        v = np.broadcast_to(v, (count,))
    except ValueError as exc:
        raise ValueError(f'{name} must be scalar or condition vector') from exc
    if not np.isfinite(v).all() or np.any(v < 0) or (positive and np.any(v <= 0)):
        raise ValueError(f'{name} must be finite and nonnegative, or positive when required')
    return v


def paired_equivalence(reference, candidate, *, absolute_tolerance,
                       repeat_ids, condition_ids, alpha=.05,
                       extra_error_margin=0., family_size=None):
    """Bonferroni simultaneous paired-t CIs inside PREDECLARED absolute tolerances.

    Rows must be genuinely paired independent repeats of the SAME scene, units,
    ROI, wavelengths and source/camera conditions. The caller establishes that
    semantic contract; IDs only prevent accidental duplicate labels. The t
    interval assumes approximately Gaussian independent repeat differences.
    extra_error_margin is an externally justified bound, NOT estimated here.
    'different' means a whole expanded interval lies outside the tolerance.
    'inconclusive' is neither equivalent nor proven beyond tolerance.
    """
    a, b = _matrix(reference, 'reference'), _matrix(candidate, 'candidate')
    if a.shape != b.shape:
        raise ValueError('reference and candidate shapes must agree')
    n, k = a.shape
    for ids, size, name in ((repeat_ids, n, 'repeat_ids'), (condition_ids, k, 'condition_ids')):
        if len(ids) != size or any(not isinstance(x, (str, int)) or isinstance(x, bool) for x in ids) or len(set(ids)) != size:
            raise ValueError(f'{name} must contain exactly {size} unique string/integer IDs')
    if isinstance(alpha, bool) or not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError('alpha must lie strictly in (0,1)')
    family = k if family_size is None else family_size
    if isinstance(family, bool) or not isinstance(family, (int, np.integer)) or family < k:
        raise ValueError('family_size must be an integer >= evaluated condition count')
    tolerance = _vector(absolute_tolerance, k, 'absolute_tolerance', positive=True)
    margin = _vector(extra_error_margin, k, 'extra_error_margin')
    d = b-a
    mean = d.mean(axis=0)
    se = d.std(axis=0, ddof=1)/np.sqrt(n)
    critical = float(student_t.ppf(1-alpha/(2*family), n-1))
    half = critical*se+margin
    lower, upper = mean-half, mean+half
    equivalent = (lower > -tolerance) & (upper < tolerance)
    different = (lower > tolerance) | (upper < -tolerance)
    rows = []
    for i, label in enumerate(condition_ids):
        rows.append({'condition': label, 'mean_difference': float(mean[i]),
                     'standard_error': float(se[i]), 'ci_lower': float(lower[i]),
                     'ci_upper': float(upper[i]), 'tolerance': float(tolerance[i]),
                     'extra_error_margin': float(margin[i]),
                     'status': 'equivalent' if equivalent[i] else 'different' if different[i] else 'inconclusive'})
    return {'schema': 'textile.observation_equivalence/1', 'repeat_count': n,
            'repeat_ids': list(repeat_ids), 'family_size': int(family),
            'alpha': float(alpha), 'critical_t': critical,
            'all_equivalent': bool(equivalent.all()), 'conditions': rows,
            'scope': 'paired repeat statistics only; reference/model/calibration validity external'}


def choose_observation_lod(candidates, *, max_relative_l2, max_relative_power,
                           max_refinement_l2):
    """Choose lowest declared cost that passes EVERY supplied named condition.

    Each candidate must report identical condition IDs, nonnegative errors and
    an independent numerical-refinement diagnostic. Passing is conditional on
    these observations; refinement difference is NOT a rigorous error bound.
    Candidate selection and acceptance cases should be separated in research.
    """
    limits = np.array([max_relative_l2, max_relative_power, max_refinement_l2], dtype=float)
    if not np.isfinite(limits).all() or np.any(limits <= 0) or not candidates:
        raise ValueError('positive finite tolerances and nonempty candidates required')
    assessed, names, condition_set = [], set(), None
    for c in candidates:
        name, cost = c['name'], float(c['cost'])
        if not isinstance(name, str) or name in names or not np.isfinite(cost) or cost <= 0:
            raise ValueError('unique candidate names and positive finite costs required')
        names.add(name)
        rows = c['conditions']
        labels = [r['condition'] for r in rows]
        if not labels or len(set(labels)) != len(labels):
            raise ValueError('nonempty unique condition IDs required')
        if condition_set is None:
            condition_set = set(labels)
        if set(labels) != condition_set:
            raise ValueError('all candidates must evaluate the same condition set')
        errors = np.array([[r['relative_l2'], r['relative_power_error'], r['refinement_l2']] for r in rows])
        if not np.isfinite(errors).all() or np.any(errors < 0):
            raise ValueError('finite nonnegative errors required; missing results cannot pass')
        worst = errors.max(axis=0)
        assessed.append({'name': name, 'cost': cost, 'accepted': bool(np.all(worst <= limits)),
                         'worst_relative_l2': float(worst[0]), 'worst_relative_power': float(worst[1]),
                         'worst_refinement_l2': float(worst[2])})
    accepted = sorted((r for r in assessed if r['accepted']), key=lambda r: (r['cost'], r['name']))
    return {'selected': accepted[0]['name'] if accepted else None,
            'candidates': assessed, 'condition_ids': sorted(condition_set),
            'scope': 'conditional empirical observation gate, not a global bound or complete fabric LOD'}


def audit_v5_radial_pair(root, *, coarse, fine, absolute_tolerance, alpha=.05):
    """Read the EXISTING v5 scalar archive; compare paired means across levels.

    Validates NPZ SHA, axes, labels, shape and finite values. Does not repeat the
    full v5 geometry/scene/source audit; use its existing verifier as well.
    No pixels or RGB channels are counted as independent replicates.
    """
    import hashlib
    import json
    from pathlib import Path

    root = Path(root)
    path = root/'optics'/'spectral_radiance.npz'
    metrics_path = root/'optics'/'optical_metrics.json'
    m = json.loads(metrics_path.read_text(encoding='utf-8'))
    if (m.get('schema_version') != 'variable_radius_optics_experiment_v5.0'
            or m.get('status') != 'rendered'
            or m.get('radiance_axes') != ['radial_segments','state','light','wavelength_nm','seed','row','column']
            or m.get('states') != ['constant_reference','incompressible_segments']
            or m.get('lights') != ['R0','R90','T45']):
        raise ValueError('unsupported/incomplete v5 scalar experiment metadata')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != m.get('spectral_radiance_sha256'):
        raise ValueError('v5 archive checksum mismatch')
    levels, waves, seeds = m['radial_segments'], m['wavelengths_nm'], m['seeds']
    for values, name in ((levels,'radial_segments'),(waves,'wavelengths_nm'),(seeds,'seeds')):
        if not values or len(set(values)) != len(values) or not np.isfinite(np.asarray(values,dtype=float)).all():
            raise ValueError('invalid ordered metadata: '+name)
    for values, name, minimum in ((levels, 'radial_segments', 3), (seeds, 'seeds', 0)):
        if any(isinstance(x, bool) or not isinstance(x, int) or x < minimum for x in values):
            raise ValueError('integer metadata required: '+name)
    if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or x <= 0 for x in waves)
            or any(b <= a for a, b in zip(waves, waves[1:]))
            or any(b <= a for a, b in zip(levels, levels[1:]))
            or isinstance(m['resolution'], bool) or not isinstance(m['resolution'], int)
            or m['resolution'] <= 0):
        raise ValueError('positive ordered wavelengths/levels and integer resolution required')
    if coarse not in levels or fine not in levels or coarse >= fine:
        raise ValueError('choose two existing increasing radial levels')
    with np.load(path, allow_pickle=False) as z:
        if set(z.files) != {'radiance'}:
            raise ValueError('v5 archive must contain only scalar radiance')
        image = z['radiance']
    expected = (len(levels),2,3,len(waves),len(seeds),m['resolution'],m['resolution'])
    if (image.shape != expected or image.dtype != np.dtype('float32')
            or not np.isfinite(image).all() or np.any(image < -1e-7)):
        raise ValueError('v5 radiance dtype/shape/sign mismatch')
    means = image.astype(float).mean(axis=(-2,-1))
    a = np.moveaxis(means[levels.index(fine)], -1, 0).reshape(len(seeds),-1)
    b = np.moveaxis(means[levels.index(coarse)], -1, 0).reshape(len(seeds),-1)
    names = [f'{state}/{light}/{wave}nm' for state in m['states'] for light in m['lights'] for wave in waves]
    out = paired_equivalence(a,b,absolute_tolerance=absolute_tolerance,
        repeat_ids=seeds,condition_ids=names,alpha=alpha)
    out.update({'reference_radial_segments': fine, 'candidate_radial_segments': coarse,
        'source_archive_sha256': digest,
        'source_metadata_sha256': hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        'observable': 'whole-image mean scalar radiance per independent seed',
        'full_v5_geometry_scene_audit_repeated': False,
        'reference_certified_converged': False, 'new_renders': 0})
    return out
