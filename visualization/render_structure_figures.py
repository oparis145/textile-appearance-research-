"""Publication figures from measured intersections of procedural textile geometry.

This module produces structural AOVs, not illuminated/radiometric renderings.
Physical pixel-center maps remain distinct from antialiased display colors.
Run ``python -m visualization.render_structure_figures --help`` for the CLI.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, patches, patheffects
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "textile.structure_figures/5.1"
BACKGROUND = np.array([0.94, 0.945, 0.95], dtype=np.float64)
UNDEFINED_ORIENTATION = np.array([0.45, 0.45, 0.45], dtype=np.float64)
ORIENTATION_CMAP = "twilight_shifted"
ORIENTATION_PHASE = .25
ORIENTATION_LUT_SIZE = 2048
HEIGHT_CMAP = "gray"
PROJECTION_THRESHOLD = 1e-8
MATERIAL_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
                   "#E69F00", "#56B4E9", "#332288", "#882255"]


def orientation_colormap():
    """A cyclic phase shift makes both warp and weft distinct from the background."""
    samples = (np.arange(ORIENTATION_LUT_SIZE) / ORIENTATION_LUT_SIZE + ORIENTATION_PHASE) % 1
    return colors.ListedColormap(matplotlib.colormaps[ORIENTATION_CMAP](samples),
                                name="twilight_quarter_cycle")


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def array_descriptor(value):
    a = np.ascontiguousarray(value)
    return {"shape": list(a.shape), "dtype": a.dtype.str,
            "sha256_c_order_bytes": hashlib.sha256(a.tobytes()).hexdigest()}


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf8", dir=path.parent,
                                     suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def save_npz_checked(path, arrays):
    """Atomic, CRC-checked save; reopen and compare every numerical array."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, suffix=".npz",
                                     delete=False) as handle:
        temporary = Path(handle.name)
        np.savez_compressed(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError("NPZ CRC failed before publishing")
    with np.load(temporary, allow_pickle=False) as saved:
        if set(saved.files) != set(arrays):
            raise ValueError("NPZ keys changed")
        for key, value in arrays.items():
            if array_descriptor(saved[key]) != array_descriptor(value):
                raise ValueError(f"NPZ round-trip changed {key}")
    os.replace(temporary, path)
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "sha256": file_sha256(path), "size_bytes": path.stat().st_size,
            "arrays": {key: array_descriptor(value) for key, value in arrays.items()}}


def orientation_angle(tangent, valid_mask, threshold=PROJECTION_THRESHOLD):
    """Unoriented XY line angle in [0, pi), with explicit vertical/absent mask."""
    t = np.asarray(tangent)
    valid = np.asarray(valid_mask, dtype=bool)
    if t.shape != (*valid.shape, 3):
        raise ValueError("tangent must have shape valid_mask.shape + (3,)")
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("projection threshold must be finite and positive")
    defined = valid & np.isfinite(t).all(axis=-1)
    defined &= np.hypot(t[..., 0], t[..., 1]) >= threshold
    angle = np.full(valid.shape, np.nan, dtype=np.float64)
    angle[defined] = np.mod(np.arctan2(t[..., 1][defined], t[..., 0][defined]), np.pi)
    return angle, defined


def antialias_straight_rgba(sample_rgb, sample_valid, supersample):
    """Average premultiplied samples, then unpremultiply for standard RGBA.

    RGB at alpha=0 is zero. On a background B, displayed RGB is
    coverage*RGB + (1-coverage)*B = mean(valid*sample_RGB + (1-valid)*B).
    Averaging straight RGBA directly would incorrectly apply alpha twice.
    """
    rgb = np.asarray(sample_rgb, dtype=np.float64)
    valid = np.asarray(sample_valid, dtype=bool)
    if rgb.shape != (*valid.shape, 3):
        raise ValueError("sample_rgb shape must be valid shape + (3,)")
    if isinstance(supersample, bool) or not isinstance(supersample, (int, np.integer)) or supersample < 1:
        raise ValueError("supersample must be a positive integer")
    if valid.ndim != 2 or any(d % supersample for d in valid.shape):
        raise ValueError("supersampled dimensions must be divisible by supersample")
    if not np.isfinite(rgb[valid]).all() or np.any(rgb[valid] < 0) or np.any(rgb[valid] > 1):
        raise ValueError("valid sample RGB must be finite in [0,1]")
    h, w = np.array(valid.shape) // supersample
    a = valid.reshape(h, supersample, w, supersample).mean(axis=(1, 3))
    premult = np.where(valid[..., None], rgb, 0)
    premult = premult.reshape(h, supersample, w, supersample, 3).mean(axis=(1, 3))
    out = np.zeros((h, w, 4), dtype=np.float32)
    np.divide(premult, a[..., None], out=out[..., :3], where=a[..., None] > 0)
    out[..., 3] = a
    return out


def create_display_maps(center, samples, supersample, height_limits_um):
    """Colorize actual samples before AA; preserve integer center material IDs."""
    valid = np.asarray(samples["valid_mask"], dtype=bool)
    n = np.asarray(samples["world_normal"])
    if not np.isfinite(n[valid]).all() or np.any(np.abs(n[valid]) > 1 + 1e-5):
        raise ValueError("valid normals must be finite in [-1,1]")
    normal_rgb = np.clip((np.nan_to_num(n) + 1) / 2, 0, 1)
    theta, defined = orientation_angle(samples["world_tangent"], valid)
    orientation_rgb = orientation_colormap()(np.nan_to_num(theta) / np.pi)[..., :3]
    orientation_rgb[valid & ~defined] = UNDEFINED_ORIENTATION
    lo, hi = map(float, height_limits_um)
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        raise ValueError("height limits must be finite and strictly increasing")
    height_um = np.asarray(samples["height_mm"]) * 1000
    if np.any(height_um[valid] < lo - 1e-6) or np.any(height_um[valid] > hi + 1e-6):
        raise ValueError("shared height range clips a valid sample")
    height_rgb = matplotlib.colormaps[HEIGHT_CMAP](np.nan_to_num((height_um - lo) / (hi - lo)))[..., :3]
    arrays = {f"{name}_rgba": antialias_straight_rgba(rgb, valid, supersample)
              for name, rgb in (("normal", normal_rgb), ("orientation", orientation_rgb),
                                ("height", height_rgb))}
    center_valid = np.asarray(center["valid_mask"], dtype=bool)
    ids = np.asarray(center["material_index"])
    material = np.zeros((*center_valid.shape, 4), dtype=np.float32)
    material[center_valid, :3] = UNDEFINED_ORIENTATION  # mixed proxy, if any
    material[center_valid, 3] = 1
    for identifier in np.unique(ids[center_valid]):
        if identifier >= 0:
            material[center_valid & (ids == identifier), :3] = colors.to_rgb(
                MATERIAL_COLORS[int(identifier) % len(MATERIAL_COLORS)])
    arrays["material_rgba"] = material
    center_theta, center_defined = orientation_angle(center["world_tangent"], center_valid)
    arrays["orientation_angle_rad"] = center_theta.astype(np.float32)
    arrays["orientation_defined_mask"] = center_defined
    coverage = np.asarray(center["coverage"])
    if not np.allclose(arrays["normal_rgba"][..., 3], coverage, rtol=0, atol=1e-7):
        raise ValueError("display alpha disagrees with independently stored sample coverage")
    stats = {
        "center_valid_pixels": int(center_valid.sum()), "center_total_pixels": int(center_valid.size),
        "center_coverage_fraction": float(center_valid.mean()),
        "supersample_valid_pixels": int(valid.sum()), "supersample_total_pixels": int(valid.size),
        "sample_coverage_fraction": float(valid.mean()),
        "center_orientation_undefined_hits": int((center_valid & ~center_defined).sum()),
        "sample_orientation_undefined_hits": int((valid & ~defined).sum()),
        "height_observed_um": [float(height_um[valid].min()), float(height_um[valid].max())],
        "height_clipped_samples": 0,
        "material_indices_on_valid_centers": np.unique(ids[center_valid]).astype(int).tolist(),
    }
    return arrays, stats


def nice_scale_length_mm(width_mm):
    """Largest 1/2/5 decimal length no greater than 23% of panel width."""
    if not np.isfinite(width_mm) or width_mm <= 0:
        raise ValueError("panel width must be finite and positive")
    target = width_mm * .23
    exponent = math.floor(math.log10(target))
    values = [coefficient * 10.0 ** power
              for power in (exponent - 1, exponent)
              for coefficient in (1, 2, 5)]
    return max(value for value in values if value <= target)


def _style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.labelsize": 10, "axes.titlesize": 12, "axes.titleweight": "semibold",
        "axes.linewidth": .6, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "savefig.facecolor": "white", "svg.fonttype": "none", "pdf.fonttype": 42})


def _show(ax, rgba, extent, title):
    ax.set_facecolor(BACKGROUND)
    ax.imshow(rgba, extent=extent, origin="upper", interpolation="nearest", aspect="equal")
    ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:])
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#CFD4D9")
    ax.set_title(title, loc="left", pad=10)


def _scale_bar(ax, extent):
    x0, x1, y0, y1 = extent
    width, height = x1 - x0, y1 - y0
    length = nice_scale_length_mm(width)
    x, y = x0 + .065 * width, y0 + .07 * height
    line, = ax.plot([x, x + length], [y, y], color="#17212B", linewidth=2.6,
                    solid_capstyle="butt", zorder=7)
    line.set_path_effects([patheffects.Stroke(linewidth=4.8, foreground="white"), patheffects.Normal()])
    ax.text(x, y + .035 * height, f"{length * 1000:g} µm", color="#17212B", fontsize=9,
            weight="semibold", path_effects=[patheffects.withStroke(linewidth=3, foreground="white")],
            zorder=8)
    return {"length_mm": length, "start_xy_mm": [x, y], "end_xy_mm": [x + length, y]}


def _glyphs(ax, arrays, extent, grid=10):
    angle = arrays["orientation_angle_rad"]
    defined = arrays["orientation_defined_mask"]
    h, w = angle.shape
    x0, x1, y0, y1 = extent
    half = (x1 - x0) / (grid * 5.0)
    glyphs = []
    for row in np.linspace(.09 * h, .91 * h, grid).astype(int):
        for column in np.linspace(.09 * w, .91 * w, grid).astype(int):
            if not defined[row, column]:
                continue
            theta = float(angle[row, column])
            x = x0 + (column + .5) / w * (x1 - x0)
            y = y1 - (row + .5) / h * (y1 - y0)
            dx, dy = half * np.cos(theta), half * np.sin(theta)
            line, = ax.plot([x - dx, x + dx], [y - dy, y + dy], color="#18212A",
                            linewidth=.8, alpha=.8, zorder=5, solid_capstyle="round")
            line.set_path_effects([patheffects.Stroke(linewidth=2, foreground="white"), patheffects.Normal()])
            glyphs.append({"pixel_row_col": [int(row), int(column)], "center_xy_mm": [x, y],
                           "theta_rad": theta, "half_length_mm": half})
    return glyphs


def _legends(fig, height_limits_um, y=.09):
    fig.text(.045, y + .035, "World normal (+Z to camera)", weight="semibold", fontsize=10)
    fig.text(.045, y - .005, "RGB = (n + 1) / 2", fontsize=9,
             color="#44515D", va="top")
    orientation_ax = fig.add_axes([.37, y + .02, .24, .023])
    orientation_bar = fig.colorbar(matplotlib.cm.ScalarMappable(
        norm=colors.Normalize(0, 180), cmap=orientation_colormap()), cax=orientation_ax,
        orientation="horizontal", ticks=[0, 45, 90, 135, 180])
    orientation_bar.outline.set_linewidth(.4)
    orientation_bar.set_label("Projected axis (°; 0° = +X)", labelpad=4, fontsize=9)
    height_ax = fig.add_axes([.695, y + .02, .24, .023])
    height_bar = fig.colorbar(matplotlib.cm.ScalarMappable(
        norm=colors.Normalize(*height_limits_um), cmap=HEIGHT_CMAP), cax=height_ax,
        orientation="horizontal")
    height_bar.outline.set_linewidth(.4)
    height_bar.set_label("World height z (µm); shared scale", labelpad=4, fontsize=9)


def _figure_artifacts(fig, stem, output_dir):
    paths = []
    for suffix in ("png", "pdf", "svg"):
        path = output_dir / f"{stem}.{suffix}"
        metadata = {"Creator": "textile-appearance-research structural map pipeline"}
        if suffix == "pdf":
            metadata.update({"CreationDate": None, "ModDate": None})
        if suffix == "svg":
            metadata["Date"] = None
        fig.savefig(path, dpi=300, metadata=metadata)
        paths.append({"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                      "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    plt.close(fig)
    return paths


def compose_figures(records, height_limits_um, output_dir):
    """Plot exclusively from preserved display arrays and explicit physical extents."""
    _style()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig_records = []
    fields = ("normal", "orientation", "height")
    labels = ("Normal", "Projected orientation", "Height")

    overview = records["overview/ply_envelope"]
    extent = overview["extent_xy_mm"]
    fig = plt.figure(figsize=(12, 4.7))
    fig.text(.035, .942, "3-ply basket weave: structural surface maps", fontsize=17, weight="semibold")
    fig.text(.035, .884, "Ply-envelope proxy  ·  original 3 × 2 basket specification", fontsize=10.5, color="#536270")
    bars = []
    for column, (field, label) in enumerate(zip(fields, labels)):
        ax = fig.add_axes([.035 + .326 * column, .245, .3, .59])
        _show(ax, overview["display"][f"{field}_rgba"], extent, f"({chr(97 + column)}) {label}")
        if column == 0:
            bars.append(_scale_bar(ax, extent))
    _legends(fig, height_limits_um, .096)
    fig.text(.035, .018, "Geometry intersections only  ·  light gray = no surface hit  ·  coverage-weighted display", fontsize=8.5, color="#5B6772")
    fig_records.append({"name": "fabric_structure_triptych", "panels": [
        {"map": "overview/ply_envelope", "field": field, "extent_xy_mm": extent} for field in fields],
        "scale_bars": bars, "files": _figure_artifacts(fig, "fabric_structure_triptych", output_dir)})

    fig = plt.figure(figsize=(12, 9.4))
    fig.text(.035, .967, "From ply envelopes to explicit fibers", fontsize=17, weight="semibold")
    fig.text(.035, .932, "Same crossing, camera and physical crop  ·  3 plies per yarn, 7 fibers per ply", fontsize=10.5, color="#536270")
    panels, bars, glyph_records = [], [], []
    for row, level in enumerate(("ply_envelope", "explicit_fiber")):
        record = records[f"zoom/{level}"]
        extent = record["extent_xy_mm"]
        row_y = .525 if row == 0 else .14
        caption = "Ply-envelope proxy" if row == 0 else "Explicit fiber surfaces"
        fig.text(.021, row_y + .18, caption, fontsize=11, weight="semibold", color="#203644",
                 rotation=90, ha="center", va="center")
        for column, (field, label) in enumerate(zip(fields, labels)):
            ax = fig.add_axes([.055 + .314 * column, row_y, .282, .36])
            _show(ax, record["display"][f"{field}_rgba"], extent, label if row == 0 else "")
            if column == 0:
                bars.append(_scale_bar(ax, extent))
            if column == 1:
                glyph_records.append({"map": f"zoom/{level}", "arrowheads": False,
                                      "samples": _glyphs(ax, record["display"], extent)})
            panels.append({"map": f"zoom/{level}", "field": field, "extent_xy_mm": extent})
    _legends(fig, height_limits_um, .052)
    fig.text(.035, .013, "Tangent = centerline direction at each represented level  ·  line glyphs have no head  ·  envelope is a geometric proxy", fontsize=8.5, color="#5B6772")
    fig_records.append({"name": "fabric_structure_hierarchy", "panels": panels,
        "scale_bars": bars, "orientation_glyphs": glyph_records,
        "files": _figure_artifacts(fig, "fabric_structure_hierarchy", output_dir)})

    fig = plt.figure(figsize=(12, 4.7))
    fig.text(.035, .942, "Fiber identity and local geometry", fontsize=17, weight="semibold")
    fig.text(.035, .884, "Integer material assignments stay attached to individual fibers across scales", fontsize=10.5, color="#536270")
    over = records["overview/explicit_fiber"]
    zoom = records["zoom/explicit_fiber"]
    panels, bars = [], []
    for column, (record, field, title) in enumerate(((over, "material", "(a) Fiber material IDs"),
            (zoom, "material", "(b) Crossing detail: IDs"), (zoom, "normal", "(c) Crossing detail: normals"))):
        ax = fig.add_axes([.035 + .326 * column, .225, .3, .6])
        _show(ax, record["display"][f"{field}_rgba"], record["extent_xy_mm"], title)
        bars.append(_scale_bar(ax, record["extent_xy_mm"]))
        map_name = "overview/explicit_fiber" if column == 0 else "zoom/explicit_fiber"
        panels.append({"map": map_name, "field": field, "extent_xy_mm": record["extent_xy_mm"]})
        if column == 0:
            x0, x1, y0, y1 = zoom["extent_xy_mm"]
            rectangle = patches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                                           edgecolor="#17212B", linewidth=1.5, zorder=6)
            rectangle.set_path_effects([patheffects.Stroke(linewidth=3, foreground="white"), patheffects.Normal()])
            ax.add_patch(rectangle)
    ids = zoom["statistics"]["material_indices_on_valid_centers"]
    handles = [patches.Patch(facecolor=MATERIAL_COLORS[i % len(MATERIAL_COLORS)],
                            label=zoom["material_labels"].get(str(i), f"Material index {i}"))
               for i in ids if i >= 0]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(.028, .102), frameon=False,
               ncol=4, fontsize=10, handlelength=1.1, columnspacing=2.0)
    fig.text(.035, .07, "Material colors are categorical labels; they are not dye colors or inferred fiber chemistry.", fontsize=9, color="#536270")
    fig.text(.035, .022, "IDs use pixel-center samples without category averaging  ·  normal colors use real supersamples  ·  light gray = no surface hit", fontsize=8.5, color="#5B6772")
    fig_records.append({"name": "fabric_structure_material_detail", "panels": panels,
        "zoom_rectangle_extent_xy_mm": zoom["extent_xy_mm"], "scale_bars": bars,
        "files": _figure_artifacts(fig, "fabric_structure_material_detail", output_dir)})
    return fig_records


def _material_labels(metadata):
    tables = metadata.get("id_tables", {})
    table = tables.get("materials", tables.get("material", tables.get("material_ids", [])))
    if isinstance(table, list):
        return {str(i): str(value.get("id", value.get("material_id", value))) if isinstance(value, dict)
                else str(value) for i, value in enumerate(table)}
    if isinstance(table, dict):
        if all(str(key).lstrip("-").isdigit() for key in table):
            return {str(key): str(value) for key, value in table.items()}
        return {str(value): str(key) for key, value in table.items()}
    return {}


def _source_files():
    names = ["visualization/render_structure_figures.py", "visualization/structure_maps.py",
             "textile_sim/hierarchy.py", "textile_sim/weave_draft.py", "textile_sim/variable_radius.py",
             "textile_sim/render.py"]
    return {name: file_sha256(ROOT / name) for name in names if (ROOT / name).is_file()}


def _display_contract(height_limits_um):
    return {
        "normal": {"source": "world_normal", "meaning": "outward geometric triangle normal at ray hit",
                   "mapping": "RGB=(n+1)/2", "world_components_rgb": ["X", "Y", "Z"],
                   "gamma_or_light_transport": "none; numeric map values are not physical display radiance"},
        "orientation": {"source": "world_tangent", "meaning": "centerline tangent of the represented ply or fiber",
                        "projection": "world XY", "angle_formula": "atan2(ty,tx) mod pi",
                        "range_rad": [0, math.pi], "period_deg": 180,
                        "colormap": ORIENTATION_CMAP, "colormap_input": "theta/pi",
                        "colormap_phase_fraction": ORIENTATION_PHASE,
                        "colormap_lut_size": ORIENTATION_LUT_SIZE,
                        "colormap_lut_rule": "base_colormap((arange(N)/N + phase_fraction) mod 1)",
                        "projection_threshold": PROJECTION_THRESHOLD,
                        "undefined_rgb": UNDEFINED_ORIENTATION.tolist(),
                        "sign_invariance": "t and -t describe the same line and share color",
                        "glyphs": "unoriented line segments from valid pixel-center tangents"},
        "height": {"source": "height_mm", "mapping": "world z * 1000; no per-panel normalization",
                   "units": "um", "shared_limits_um": list(map(float, height_limits_um)),
                   "colormap": HEIGHT_CMAP, "clipped_samples_allowed": 0},
        "material": {"source": "material_index at pixel center", "palette_hex": MATERIAL_COLORS,
                     "palette_rule": "nonnegative integer index modulo palette length",
                     "meaning": "synthetic source assignments, not material inference or dye colors",
                     "antialias_categories": False, "mixed_proxy_rgb": UNDEFINED_ORIENTATION.tolist()},
        "background_rgb": BACKGROUND.tolist(),
        "antialias": {"source": "actual regular-grid ray-hit supersamples",
            "order": "map each sample to RGB, average premultiplied RGB and hit alpha, then unpremultiply",
            "storage": "straight RGBA float32; alpha=coverage; RGB=0 where alpha=0",
            "equation": "RGB=mean(hit*sample_rgb)/mean(hit); alpha=mean(hit)",
            "composite_equation": "alpha*RGB+(1-alpha)*B = mean(hit*sample_rgb+(1-hit)*B)",
            "normal_average_is_unit_vector": False,
            "reproducible_sources": "display_sources.npz preserves hit mask, normal, tangent and height supersamples"},
        "camera": {"type": "orthographic top down", "view_direction": [0, 0, -1],
                   "right": [1, 0, 0], "up": [0, 1, 0], "array_row_zero": "largest world y",
                   "matplotlib_origin": "upper", "extent_order": ["xmin", "xmax", "ymin", "ymax"],
                   "all_lengths": "mm; scale bars explicitly labelled um"},
    }


def run_pipeline(spec_path, data_dir, figure_dir, resolution=640, supersample=2,
                 radial_segments=64, zoom_width_mm=.22):
    from textile_sim.hierarchy import FabricSpec, build_hierarchy
    from visualization.structure_maps import (build_structure_surface, make_topdown_camera,
                                              trace_structure_maps, save_structure_maps)
    started = time.perf_counter()
    sources = _source_files()
    spec_path, data_dir, figure_dir = map(lambda p: Path(p).resolve(), (spec_path, data_dir, figure_dir))
    spec_dict = json.loads(spec_path.read_text())
    spec = FabricSpec.from_dict(spec_dict)
    geometry = build_hierarchy(spec)
    data_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(data_dir / "input_spec.json", spec_dict)
    # Crops are fixed from declared crossing pitches, not image content fitting.
    width = spec.warp_count * spec.warp_pitch_mm
    height = spec.weft_count * spec.weft_pitch_mm
    overview = [-width / 2, width / 2, -height / 2, height / 2]
    central_warp, central_weft = spec.warp_count // 2, spec.weft_count // 2
    cx = (central_warp - .5 * (spec.warp_count - 1)) * spec.warp_pitch_mm
    cy = (central_weft - .5 * (spec.weft_count - 1)) * spec.weft_pitch_mm
    zoom = [cx - zoom_width_mm / 2, cx + zoom_width_mm / 2,
            cy - zoom_width_mm / 2, cy + zoom_width_mm / 2]
    records = {}
    height_limits_um = None
    for level in ("ply_envelope", "explicit_fiber"):
        print(f"Building {level} surface", flush=True)
        surface = build_structure_surface(geometry, level=level, radial_segments=radial_segments,
                                          envelope_scale=1.0)
        bounds = np.asarray(surface.bounds_mm, dtype=float)
        if bounds.shape != (2, 3):
            raise ValueError("surface bounds must be (2,3) min/max XYZ")
        # Set one rounded range before tracing; reject any later level outside it.
        # A swept ply proxy is not assumed to enclose every oblique child surface.
        if height_limits_um is None:
            height_limits_um = [math.floor(bounds[0, 2] * 1000 / 10) * 10,
                                math.ceil(bounds[1, 2] * 1000 / 10) * 10]
        if bounds[0, 2] * 1000 < height_limits_um[0] or bounds[1, 2] * 1000 > height_limits_um[1]:
            raise ValueError("a level exceeds the predeclared shared height range")
        for role, extent in (("overview", overview), ("zoom", zoom)):
            pixel_height = max(8, round(resolution * (extent[3] - extent[2]) / (extent[1] - extent[0])))
            camera = make_topdown_camera(surface.bounds_mm, resolution=(pixel_height, resolution),
                                         extent_xy_mm=extent, padding_fraction=0)
            print(f"Tracing {role}/{level}: {pixel_height} x {resolution}, SS={supersample}", flush=True)
            result = trace_structure_maps(surface, camera, supersample=supersample)
            folder = data_dir / role / level
            save_structure_maps(folder, result, include_supersampled=False)
            raw_path, metadata_path = folder / "structure_maps.npz", folder / "structure_maps.json"
            samples = {key: result.supersampled[key] for key in (
                "valid_mask", "world_normal", "world_tangent", "height_mm")}
            display, statistics = create_display_maps(result.arrays, samples, supersample, height_limits_um)
            samples_descriptor = save_npz_checked(folder / "display_sources.npz", samples)
            display_descriptor = save_npz_checked(folder / "display_rgba.npz", display)
            record = {"role": role, "level": level, "extent_xy_mm": list(map(float, extent)),
                "resolution_hw": [pixel_height, resolution], "supersample": int(supersample),
                "radial_segments": int(radial_segments), "statistics": statistics,
                "raw_arrays": {"path": str(raw_path.relative_to(ROOT)) if raw_path.is_relative_to(ROOT) else str(raw_path),
                               "sha256": file_sha256(raw_path), "size_bytes": raw_path.stat().st_size},
                "raw_metadata": {"path": str(metadata_path.relative_to(ROOT)) if metadata_path.is_relative_to(ROOT) else str(metadata_path),
                                 "sha256": file_sha256(metadata_path), "size_bytes": metadata_path.stat().st_size},
                "display_sources": samples_descriptor, "display_arrays": display_descriptor,
                "material_labels": _material_labels(result.metadata),
                "camera": result.metadata.get("camera", {}), "display": display}
            records[f"{role}/{level}"] = record
            print(f"Saved {role}/{level}, coverage={statistics['sample_coverage_fraction']:.6f}", flush=True)
            del result, samples
            gc.collect()
        del surface
        gc.collect()
    figure_records = compose_figures(records, height_limits_um, figure_dir)
    if _source_files() != sources:
        raise RuntimeError("producer source changed during structure-map generation")
    spec_saved = data_dir / "input_spec.json"
    manifest = {"schema": SCHEMA, "status": "completed", "kind": "structural_AOV_visualization",
        "not_a_radiance_render": True, "elapsed_seconds": time.perf_counter() - started,
        "producer_sources_sha256": sources,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                    "matplotlib": matplotlib.__version__},
        "input_spec": {"path": str(spec_saved.relative_to(ROOT)) if spec_saved.is_relative_to(ROOT) else str(spec_saved),
                       "sha256": file_sha256(spec_saved), "original_path": str(spec_path.relative_to(ROOT)) if spec_path.is_relative_to(ROOT) else str(spec_path),
                       "original_sha256": file_sha256(spec_path)},
        "geometry": {"yarns": len(geometry.yarns), "plies": len(geometry.plies),
                     "fibers": len(geometry.fiber_records), "draft": spec_dict["draft"],
                     "radial_segments": int(radial_segments), "metadata": geometry.metadata},
        "crossing_zoom": {"warp_index": central_warp, "weft_index": central_weft,
                          "center_xy_mm": [cx, cy], "extent_xy_mm": zoom},
        "encoding": _display_contract(height_limits_um),
        "input_maps": {key: {k: v for k, v in rec.items() if k != "display"} for key, rec in records.items()},
        "figures": figure_records,
        "reproduction": {"cwd": "repository root", "full_command": ["python", "-m",
            "visualization.render_structure_figures", "--spec", str(spec_path.relative_to(ROOT)) if spec_path.is_relative_to(ROOT) else str(spec_path),
            "--data-dir", str(data_dir.relative_to(ROOT)) if data_dir.is_relative_to(ROOT) else str(data_dir),
            "--figure-dir", str(figure_dir.relative_to(ROOT)) if figure_dir.is_relative_to(ROOT) else str(figure_dir),
            "--resolution", str(resolution), "--supersample", str(supersample),
            "--radial-segments", str(radial_segments), "--zoom-width-mm", str(zoom_width_mm)],
            "plot_only_command": ["python", "-m", "visualization.render_structure_figures", "--replot-from",
                                  str((figure_dir / "figure_manifest.json").relative_to(ROOT)) if figure_dir.is_relative_to(ROOT) else str(figure_dir / "figure_manifest.json")],
            "plot_only_retraces_geometry": False},
        "scope": ["The envelope and explicit-fiber surfaces are distinct geometric representations.",
            "The ply map's tangent is not the analytic twist-rotated fiber orientation used in FabricGen.",
            "Geometry is procedural and has not been fitted to a physical specimen.",
            "No light transport, scattering, optical material inference or radiance accuracy is implied.",
            "v0.5 optical experiments are unchanged; these maps do not increase their sample counts."]}
    atomic_json(figure_dir / "figure_manifest.json", manifest)
    return manifest


def replot(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unsupported figure manifest schema")
    records = {}
    for key, record in manifest["input_maps"].items():
        descriptor = record["display_arrays"]
        path = Path(descriptor["path"])
        path = path if path.is_absolute() else ROOT / path
        if file_sha256(path) != descriptor["sha256"]:
            raise ValueError(f"display file hash mismatch: {key}")
        with np.load(path, allow_pickle=False) as arrays:
            display = {name: arrays[name] for name in arrays.files}
        if {name: array_descriptor(value) for name, value in display.items()} != descriptor["arrays"]:
            raise ValueError(f"display semantic hash mismatch: {key}")
        records[key] = {**record, "display": display}
    manifest["figures"] = compose_figures(records,
        manifest["encoding"]["height"]["shared_limits_um"], manifest_path.parent)
    manifest["plot_source_sha256"] = file_sha256(__file__)
    atomic_json(manifest_path, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=ROOT / "examples/hierarchy/basket_rectangular_three_ply.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/structure_maps_v5_1")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "figures/structure_v5_1")
    parser.add_argument("--resolution", type=int, default=640, help="horizontal pixels; vertical count preserves physical aspect")
    parser.add_argument("--supersample", type=int, default=2)
    parser.add_argument("--radial-segments", type=int, default=64)
    parser.add_argument("--zoom-width-mm", type=float, default=.22)
    parser.add_argument("--replot-from", type=Path, help="recompose preserved displays; no geometry tracing")
    args = parser.parse_args(argv)
    if args.replot_from is not None:
        result = replot(args.replot_from)
    else:
        if args.resolution < 8 or args.supersample < 1 or args.radial_segments < 8:
            parser.error("resolution>=8, supersample>=1 and radial-segments>=8 are required")
        if not np.isfinite(args.zoom_width_mm) or args.zoom_width_mm <= 0:
            parser.error("zoom width must be finite and positive")
        result = run_pipeline(args.spec, args.data_dir, args.figure_dir, args.resolution,
                              args.supersample, args.radial_segments, args.zoom_width_mm)
    print(json.dumps({"status": result["status"], "maps": len(result["input_maps"]),
                      "figures": len(result["figures"]), "kind": result["kind"]}), flush=True)


if __name__ == "__main__":
    main()
