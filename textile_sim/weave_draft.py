"""Validated periodic woven drafts, independent of geometry and appearance.

Rows are weft picks, columns are warp ends. ``1`` means warp above weft.
Only a single layer of mutually perpendicular warp/weft families is represented.
An arbitrary binary draft is NOT a certificate of loom/manufacturing feasibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import gcd
import numbers
from typing import Sequence

import numpy as np


def _binary_matrix(values):
    rows = tuple(tuple(row) for row in values)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("draft must be a nonempty rectangular matrix")
    if any(not isinstance(v, (numbers.Integral, np.bool_)) or int(v) not in (0, 1)
           for row in rows for v in row):
        raise ValueError("draft entries must be integer/bool zero or one")
    return tuple(tuple(int(v) for v in row) for row in rows)


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def cyclic_run_lengths(values, target):
    """Lengths of maximal target-valued runs on a circle; no double counting.

    A constant row has one run equal to the repeat length. This is a lower
    bound on an unbound float in an infinitely repeated draft, reported
    separately by :meth:`WeaveDraft.diagnostics`.
    """
    a = np.asarray(values)
    if a.ndim != 1 or len(a) == 0 or target not in (0, 1):
        raise ValueError("nonempty one-dimensional binary sequence required")
    if not np.all((a == 0) | (a == 1)):
        raise ValueError("sequence must be binary")
    hit = a == target
    if not np.any(hit):
        return ()
    if np.all(hit):
        return (len(a),)
    starts = np.flatnonzero(hit & ~np.roll(hit, 1))
    result = []
    for start in starts:
        n = 1
        while hit[(start+n) % len(hit)]:
            n += 1
        result.append(n)
    return tuple(result)


@dataclass(frozen=True)
class WeaveDraft:
    matrix: tuple[tuple[int, ...], ...]
    name: str = "custom"

    def __post_init__(self):
        object.__setattr__(self, "matrix", _binary_matrix(self.matrix))
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("draft name must be nonempty")

    @property
    def weft_repeat(self):
        return len(self.matrix)

    @property
    def warp_repeat(self):
        return len(self.matrix[0])

    @property
    def shape(self):
        return self.weft_repeat, self.warp_repeat

    def as_array(self):
        return np.asarray(self.matrix, dtype=np.int8)

    def crossing(self, warp_index, weft_index):
        """Periodic lookup, including negative indices used for patch padding."""
        if (not isinstance(warp_index, numbers.Integral)
                or not isinstance(weft_index, numbers.Integral)):
            raise TypeError("crossing indices must be integers")
        return bool(self.matrix[weft_index % self.weft_repeat]
                    [warp_index % self.warp_repeat])

    def expanded(self, weft_count, warp_count):
        nr = _positive_int(weft_count, "weft_count")
        nc = _positive_int(warp_count, "warp_count")
        a = self.as_array()
        return a[np.arange(nr)[:, None] % self.weft_repeat,
                 np.arange(nc)[None, :] % self.warp_repeat]

    def transposed(self):
        """Exchange warp and weft while preserving physical over/under order.

        New warp is old weft, so transposition also complements the bits.
        """
        return WeaveDraft(tuple(map(tuple, 1-self.as_array().T)),
                          f"{self.name}:families_exchanged")

    def diagnostics(self):
        a = self.as_array()
        constant_warps = [int(j) for j in range(a.shape[1])
                          if np.all(a[:, j] == a[0, j])]
        constant_wefts = [int(i) for i in range(a.shape[0])
                          if np.all(a[i] == a[i, 0])]
        runs = {}
        for family, seqs in (("warp", a.T), ("weft", a)):
            for value in (0, 1):
                values = [v for seq in seqs for v in cyclic_run_lengths(seq, value)]
                runs[f"{family}_value_{value}_max_run_in_repeat"] = max(values, default=0)
        return {
            "weft_repeat": self.weft_repeat,
            "warp_repeat": self.warp_repeat,
            "warp_top_fraction": float(a.mean()),
            "unbound_warp_indices": constant_warps,
            "unbound_weft_indices": constant_wefts,
            "every_yarn_interlaces_in_repeat": not constant_warps and not constant_wefts,
            "run_lengths": runs,
            "scope": "Binary single-layer topology diagnostics; no manufacturing certificate.",
        }

    def to_liftplan(self):
        """Exact binary lift-plan factorization by grouping identical columns.

        Threading entries are zero-based shaft IDs. ``liftplan[pick][shaft]``
        says whether that shaft is raised. This is not an optimized treadle
        tie-up and does not check loom limits or finite yarn thickness.
        """
        columns = list(zip(*self.matrix))
        lookup, threading, unique = {}, [], []
        for column in columns:
            if column not in lookup:
                lookup[column] = len(unique)
                unique.append(column)
            threading.append(lookup[column])
        liftplan = [list(row) for row in zip(*unique)]
        return {"threading": threading, "liftplan": liftplan,
                "shaft_count": len(unique), "index_base": 0}

    @classmethod
    def from_liftplan(cls, threading: Sequence[int], liftplan, name="liftplan"):
        lift = np.asarray(_binary_matrix(liftplan), dtype=np.int8)
        if len(threading) == 0:
            raise ValueError("threading must not be empty")
        if any(isinstance(i, bool) or not isinstance(i, numbers.Integral)
               or i < 0 or i >= lift.shape[1] for i in threading):
            raise ValueError("threading must contain valid zero-based shaft IDs")
        return cls(tuple(map(tuple, lift[:, list(threading)])), name)

    def to_dict(self):
        return {"name": self.name, "matrix": [list(row) for row in self.matrix],
                "row_axis": "weft", "column_axis": "warp", "one_means": "warp_over"}

    @classmethod
    def from_dict(cls, value):
        if value.get("row_axis", "weft") != "weft" or value.get("column_axis", "warp") != "warp":
            raise ValueError("unsupported draft axis convention")
        if value.get("one_means", "warp_over") != "warp_over":
            raise ValueError("unsupported crossing convention")
        unknown = set(value)-{"name", "matrix", "row_axis", "column_axis", "one_means"}
        if unknown:
            raise ValueError(f"unknown draft fields: {sorted(unknown)}")
        return cls(value["matrix"], value.get("name", "custom"))

    @classmethod
    def plain(cls):
        return cls(((1, 0), (0, 1)), "plain")

    @classmethod
    def twill(cls, over=2, under=2, step=1):
        over, under = _positive_int(over, "over"), _positive_int(under, "under")
        n = over+under
        if not isinstance(step, numbers.Integral) or step == 0:
            raise ValueError("twill step must be a nonzero integer")
        rows = tuple(tuple(int((j-step*i) % n < over) for j in range(n)) for i in range(n))
        return cls(rows, f"twill_{over}_{under}_step{step}")

    @classmethod
    def basket(cls, warp_group=2, weft_group=2):
        gw = _positive_int(warp_group, "warp_group")
        gf = _positive_int(weft_group, "weft_group")
        a = np.repeat(np.repeat(np.asarray(((1, 0), (0, 1))), gf, axis=0), gw, axis=1)
        return cls(tuple(map(tuple, a)), f"basket_{gw}x{gf}")

    @classmethod
    def satin(cls, repeat=5, step=2, warp_faced=True):
        n = _positive_int(repeat, "repeat")
        if n < 5 or not isinstance(step, numbers.Integral) or not 1 < step < n-1 or gcd(n, step) != 1:
            raise ValueError("regular satin requires n>=5, 1<step<n-1 and coprime step")
        a = np.asarray([[int((j-step*i) % n != 0) for j in range(n)] for i in range(n)])
        if not warp_faced:
            a = 1-a
        return cls(tuple(map(tuple, a)), f"satin_{n}_step{step}")


def quintic_blend(u):
    """Monotone endpoint blend with zero first and second derivatives."""
    u = np.asarray(u, dtype=float)
    return u*u*u*(10+u*(-15+6*u))


def periodic_crossing_height(position_mm, *, draft: WeaveDraft, family: str,
                             yarn_index: int, crossing_pitch_mm: float,
                             amplitude_mm: float, derivative: int = 0):
    """C2 crimp interpolating exact over/under heights without overshoot.

    Position zero is crossing index zero, before world centering. The two
    families may have different crossing pitches and crimp amplitudes.
    """
    if family not in ("warp", "weft"):
        raise ValueError("family must be warp or weft")
    if (not np.isfinite(crossing_pitch_mm) or crossing_pitch_mm <= 0
            or not np.isfinite(amplitude_mm) or amplitude_mm < 0):
        raise ValueError("finite positive pitch and nonnegative amplitude required")
    if derivative not in (0, 1, 2):
        raise ValueError("only derivatives zero, one, two are supported")
    q = np.asarray(position_mm, dtype=float)/crossing_pitch_mm
    if not np.all(np.isfinite(q)):
        raise ValueError("positions must be finite")
    k = np.floor(q).astype(np.int64)
    u = q-k
    a = draft.as_array()
    if family == "warp":
        b0 = a[k % draft.weft_repeat, yarn_index % draft.warp_repeat]
        b1 = a[(k+1) % draft.weft_repeat, yarn_index % draft.warp_repeat]
        sign = 1.
    else:
        b0 = a[yarn_index % draft.weft_repeat, k % draft.warp_repeat]
        b1 = a[yarn_index % draft.weft_repeat, (k+1) % draft.warp_repeat]
        sign = -1.
    z0 = sign*amplitude_mm*(2*b0-1)
    z1 = sign*amplitude_mm*(2*b1-1)
    if derivative == 0:
        return z0+(z1-z0)*quintic_blend(u)
    if derivative == 1:
        return (z1-z0)*30*u*u*(1-u)*(1-u)/crossing_pitch_mm
    return (z1-z0)*60*u*(1-u)*(1-2*u)/(crossing_pitch_mm**2)
