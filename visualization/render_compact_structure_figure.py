"""A separately labelled compact basket demonstration; canonical inputs stay fixed."""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import platform
import time

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from visualization.render_structure_figures import (
    ROOT, SCHEMA, _display_contract, _figure_artifacts, _legends, _material_labels,
    _scale_bar, _show, _source_files, _style, array_descriptor, atomic_json,
    create_display_maps, file_sha256, save_npz_checked, compose_figures,
)


def _path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def compose_compact(record, height_limits_um, figure_dir):
    _style()
    figure_dir = Path(figure_dir)
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure = plt.figure(figsize=(12, 4.7))
    figure.text(.035, .942, "Compact 3-ply basket: structural surface maps", fontsize=17, weight="semibold")
    figure.text(.035, .884, "Ply-envelope proxy  ·  separate demonstration specification  ·  actual geometry intersections",
                fontsize=10.3, color="#536270")
    fields = ("normal", "orientation", "height")
    titles = ("Normal", "Projected orientation", "Height")
    bars = []
    for column, (field, title) in enumerate(zip(fields, titles)):
        axes = figure.add_axes([.035 + .326 * column, .245, .3, .59])
        _show(axes, record["display"][f"{field}_rgba"], record["extent_xy_mm"], f"({chr(97 + column)}) {title}")
        if column == 0:
            bars.append(_scale_bar(axes, record["extent_xy_mm"]))
    _legends(figure, height_limits_um, .096)
    figure.text(.035, .018, "Unlit structural fields  ·  light gray = no surface hit  ·  no changes to the original basket or v0.5 optical experiments",
                fontsize=8.4, color="#5B6772")
    return [{"name": "compact_structure_triptych", "panels": [
        {"map": "overview/ply_envelope", "field": field,
         "extent_xy_mm": record["extent_xy_mm"]} for field in fields],
        "scale_bars": bars, "files": _figure_artifacts(figure, "compact_structure_triptych", figure_dir)}]


def _compose_family(records, limits, figure_dir):
    # Generic hierarchy/ID figures already label represented levels correctly.
    # Replace the original-input overview with a compact-specific triptych.
    generic = compose_figures(records, limits, figure_dir)
    compact = compose_compact(records["overview/ply_envelope"], limits, figure_dir)
    for record in generic[0]["files"]:
        obsolete = Path(record["path"])
        if not obsolete.is_absolute():
            obsolete = ROOT / obsolete
        obsolete.unlink()
    return compact + generic[1:]


def render_compact(spec_path, data_dir, figure_dir, resolution=640, supersample=2,
                   radial_segments=64, zoom_width_mm=.16):
    from textile_sim.hierarchy import FabricSpec, build_hierarchy
    from visualization.structure_maps import (build_structure_surface, make_topdown_camera,
                                              trace_structure_maps, save_structure_maps)
    started = time.perf_counter()
    sources = {**_source_files(), _path(__file__): file_sha256(__file__)}
    spec_path, data_dir, figure_dir = [Path(p).resolve() for p in (spec_path, data_dir, figure_dir)]
    spec_dict = json.loads(spec_path.read_text())
    spec = FabricSpec.from_dict(spec_dict)
    geometry = build_hierarchy(spec)
    data_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(data_dir / "input_spec.json", spec_dict)
    width, height = spec.warp_count * spec.warp_pitch_mm, spec.weft_count * spec.weft_pitch_mm
    overview = [-width / 2, width / 2, -height / 2, height / 2]
    central_warp, central_weft = spec.warp_count // 2, spec.weft_count // 2
    cx = (central_warp - .5 * (spec.warp_count - 1)) * spec.warp_pitch_mm
    cy = (central_weft - .5 * (spec.weft_count - 1)) * spec.weft_pitch_mm
    zoom = [cx - zoom_width_mm / 2, cx + zoom_width_mm / 2,
            cy - zoom_width_mm / 2, cy + zoom_width_mm / 2]
    records, limits = {}, None
    for level in ("ply_envelope", "explicit_fiber"):
        print(f"Building separate compact demonstration: {level}", flush=True)
        surface = build_structure_surface(geometry, level=level, radial_segments=radial_segments)
        if limits is None:
            limits = [math.floor(surface.bounds_mm[0, 2] * 100) * 10,
                      math.ceil(surface.bounds_mm[1, 2] * 100) * 10]
        if surface.bounds_mm[0, 2] * 1000 < limits[0] or surface.bounds_mm[1, 2] * 1000 > limits[1]:
            raise ValueError("compact representation exceeds common height scale")
        for role, extent in (("overview", overview), ("zoom", zoom)):
            pixel_height = max(8, round(resolution * (extent[3] - extent[2]) / (extent[1] - extent[0])))
            camera = make_topdown_camera(surface.bounds_mm, resolution=(pixel_height, resolution),
                                         extent_xy_mm=extent, padding_fraction=0)
            print(f"Tracing compact {role}/{level}: {pixel_height}x{resolution}, SS={supersample}", flush=True)
            result = trace_structure_maps(surface, camera, supersample=supersample)
            folder = data_dir / role / level
            save_structure_maps(folder, result, include_supersampled=False)
            samples = {key: result.supersampled[key] for key in (
                "valid_mask", "world_normal", "world_tangent", "height_mm")}
            display, stats = create_display_maps(result.arrays, samples, supersample, limits)
            sources_descriptor = save_npz_checked(folder / "display_sources.npz", samples)
            display_descriptor = save_npz_checked(folder / "display_rgba.npz", display)
            files = {}
            for key, name in (("raw_arrays", "structure_maps.npz"), ("raw_metadata", "structure_maps.json")):
                path = folder / name
                files[key] = {"path": _path(path), "sha256": file_sha256(path), "size_bytes": path.stat().st_size}
            records[f"{role}/{level}"] = {"role": role, "level": level, "extent_xy_mm": extent,
                "resolution_hw": [pixel_height, resolution], "supersample": supersample,
                "radial_segments": radial_segments, "statistics": stats,
                **files, "display_sources": sources_descriptor, "display_arrays": display_descriptor,
                "material_labels": _material_labels(result.metadata), "camera": result.metadata["camera"],
                "display": display}
            print(f"Saved compact {role}/{level}: coverage={stats['sample_coverage_fraction']:.6f}", flush=True)
            del result, samples
            gc.collect()
        del surface
        gc.collect()
    figures = _compose_family(records, limits, figure_dir)
    if sources != {**_source_files(), _path(__file__): file_sha256(__file__)}:
        raise RuntimeError("producer source changed during compact geometry visualization")
    saved_spec = data_dir / "input_spec.json"
    manifest = {"schema": SCHEMA, "status": "completed", "kind": "structural_AOV_visualization",
        "not_a_radiance_render": True, "demonstration_variant": "separate compact specification",
        "elapsed_seconds": time.perf_counter() - started, "producer_sources_sha256": sources,
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "input_spec": {"path": _path(saved_spec), "sha256": file_sha256(saved_spec),
                       "original_path": _path(spec_path), "original_sha256": file_sha256(spec_path)},
        "geometry": {"yarns": len(geometry.yarns), "plies": len(geometry.plies),
                     "fibers": len(geometry.fiber_records), "draft": spec_dict["draft"],
                     "radial_segments": radial_segments, "metadata": geometry.metadata},
        "crossing_zoom": {"warp_index": central_warp, "weft_index": central_weft,
                          "center_xy_mm": [cx, cy], "extent_xy_mm": zoom},
        "encoding": _display_contract(limits),
        "input_maps": {key: {k: value for k, value in record.items() if k != "display"}
                       for key, record in records.items()},
        "figures": figures,
        "reproduction": {"cwd": "repository root", "full_command": ["python", "-m",
            "visualization.render_compact_structure_figure", "--spec", _path(spec_path),
            "--data-dir", _path(data_dir), "--figure-dir", _path(figure_dir),
            "--resolution", str(resolution), "--supersample", str(supersample),
            "--radial-segments", str(radial_segments), "--zoom-width-mm", str(zoom_width_mm)],
            "plot_only_command": ["python", "-m", "visualization.render_compact_structure_figure",
                                  "--replot-from", _path(figure_dir / "figure_manifest.json")],
            "plot_only_retraces_geometry": False},
        "scope": ["A separate compact demonstration input, not a revised optical experiment or fitted specimen.",
                  "Ply envelopes and explicit fibers are distinct geometric representations.",
                  "The draft is a 2-by-2 basket; 3-ply denotes the number of plies per yarn.",
                  "No radiance, material identification, measured color or FabricGen numerical replication is implied."]}
    design_path = spec_path.with_name(spec_path.stem + "_design_audit.json")
    if design_path.is_file():
        manifest["design_audit_reference"] = {"path": _path(design_path), "sha256": file_sha256(design_path)}
    atomic_json(figure_dir / "figure_manifest.json", manifest)
    print(json.dumps({"status": "completed", "maps": len(records), "figures": len(figures),
                      "variant": "compact demonstration"}), flush=True)
    return manifest

def replot_compact(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != SCHEMA or not manifest.get("demonstration_variant"):
        raise ValueError("a compact structure figure manifest is required")
    records = {}
    for key, record in manifest["input_maps"].items():
        descriptor = record["display_arrays"]
        source = Path(descriptor["path"])
        source = source if source.is_absolute() else ROOT / source
        if file_sha256(source) != descriptor["sha256"]:
            raise ValueError("saved compact display hash mismatch")
        with np.load(source, allow_pickle=False) as saved:
            display = {name: saved[name] for name in saved.files}
        if descriptor["arrays"] != {name: array_descriptor(value) for name, value in display.items()}:
            raise ValueError("compact display array semantic hash mismatch")
        records[key] = {**record, "display": display}
    manifest["figures"] = _compose_family(records, manifest["encoding"]["height"]["shared_limits_um"], path.parent)
    manifest["plot_source_sha256"] = file_sha256(__file__)
    atomic_json(path, manifest)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/structure_maps_v5_1/compact")
    parser.add_argument("--figure-dir", type=Path, default=ROOT / "figures/structure_v5_1/compact")
    parser.add_argument("--resolution", type=int, default=640)
    parser.add_argument("--supersample", type=int, default=2)
    parser.add_argument("--radial-segments", type=int, default=64)
    parser.add_argument("--zoom-width-mm", type=float, default=.16)
    parser.add_argument("--replot-from", type=Path)
    args = parser.parse_args(argv)
    if args.replot_from:
        replot_compact(args.replot_from)
    else:
        if args.spec is None or args.resolution < 8 or args.supersample < 1 or args.radial_segments < 8:
            parser.error("provide --spec; require resolution>=8, supersample>=1, radial-segments>=8")
        if not np.isfinite(args.zoom_width_mm) or args.zoom_width_mm <= 0:
            parser.error("zoom width must be finite and positive")
        render_compact(args.spec, args.data_dir, args.figure_dir, args.resolution,
                       args.supersample, args.radial_segments, args.zoom_width_mm)


if __name__ == "__main__":
    main()
