"""Publish saved textile structure figures through verified in-memory containers.

This output-only adapter leaves all original generation code and raw map bytes
unchanged. Frozen composers are temporarily given an exporter that serializes
each complete figure to BytesIO, validates it, and stages bytes before atomic
publication. No geometry tracing or physical field/color recomputation occurs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from visualization import render_structure_figures as canonical
from visualization import render_compact_structure_figure as compact

ROOT = canonical.ROOT
FINALIZATION_SCHEMA = "textile.structure_figure_publication/5.1"


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _path(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def validate_container(payload, suffix):
    """Validate complete PNG/SVG containers and PDF header/end marker.

    PDF page parsing/rasterization is a separate optional environment QA step;
    this package deliberately does not add a PyMuPDF runtime dependency.
    """
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("a nonempty immutable bytes payload is required")
    suffix = suffix.lower().lstrip(".")
    try:
        if suffix == "png":
            with Image.open(io.BytesIO(payload)) as picture:
                if picture.format != "PNG":
                    raise ValueError("not a PNG container")
                picture.verify()
            with Image.open(io.BytesIO(payload)) as picture:
                picture.load()
                size = list(picture.size)
                if min(size) <= 0:
                    raise ValueError("empty PNG")
            return {"format": "png", "full_decode": True, "dimensions_wh": size}
        if suffix == "svg":
            root = ET.fromstring(payload)
            if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
                raise ValueError("not an SVG root")
            return {"format": "svg", "xml_parse": True,
                    "width": root.attrib.get("width"), "height": root.attrib.get("height")}
        if suffix == "pdf":
            if not payload.startswith(b"%PDF-") or not payload.rstrip().endswith(b"%%EOF"):
                raise ValueError("PDF header or terminal EOF marker is missing")
            return {"format": "pdf", "header_and_terminal_eof": True,
                    "full_pdf_parser_required_here": False}
    except (OSError, SyntaxError, ET.ParseError) as error:
        raise ValueError(f"invalid {suffix} container: {error}") from error
    raise ValueError(f"unsupported figure container: {suffix}")


def atomic_publish(path, payload, expected_sha256):
    """Do not alter destination unless the candidate bytes match their digest."""
    path = Path(path)
    if _sha(payload) != expected_sha256:
        raise ValueError("candidate payload does not match expected SHA256")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".publish-",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        actual = path.read_bytes()
        if actual != payload or _sha(actual) != expected_sha256:
            raise RuntimeError(f"atomic publication readback failed: {path}")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _source_hashes():
    files = [Path(__file__), Path(canonical.__file__), Path(compact.__file__)]
    return {_path(path): canonical.file_sha256(path) for path in files}


class MemoryFigureExporter:
    def __init__(self, *, compact_case=False):
        self.compact_case = compact_case
        self.payloads = {}
        self.layout_adjustments = []

    def __call__(self, figure, stem, output_directory):
        # The frozen compact composer makes a generic intermediate triptych.
        # It is never serialized or written; only the labelled compact version
        # is accepted. Returning no files keeps the frozen cleanup a no-op.
        if self.compact_case and stem == "fabric_structure_triptych":
            plt.close(figure)
            return []
        if self.compact_case and stem == "compact_structure_triptych":
            for text in figure.texts:
                if text.get_text().startswith("Ply-envelope proxy  ·  separate demonstration specification"):
                    previous = list(text.get_position())
                    text.set_position((.035, .192))
                    self.layout_adjustments.append({
                        "figure": stem, "artist": "compact explanatory subtitle",
                        "from_figure_xy": previous, "to_figure_xy": [.035, .192],
                        "reason": "avoid overlap with square-panel titles; move into gap below maps",
                        "map_data_or_camera_changed": False})
        records = []
        try:
            for suffix in ("png", "pdf", "svg"):
                metadata = {"Creator": "textile-appearance-research structural map pipeline"}
                if suffix == "pdf":
                    metadata.update({"CreationDate": None, "ModDate": None})
                if suffix == "svg":
                    metadata["Date"] = None
                buffer = io.BytesIO()
                figure.savefig(buffer, format=suffix, dpi=300, metadata=metadata)
                payload = buffer.getvalue()
                validation = validate_container(payload, suffix)
                path = Path(output_directory).resolve() / f"{stem}.{suffix}"
                if path in self.payloads:
                    raise ValueError(f"duplicate staged artifact: {path}")
                self.payloads[path] = payload
                records.append({"path": _path(path), "sha256": _sha(payload),
                                "size_bytes": len(payload), "container_validation": validation})
        finally:
            plt.close(figure)
        return records


@contextmanager
def intercept_exporters(exporter):
    old_canonical, old_compact = canonical._figure_artifacts, compact._figure_artifacts
    canonical._figure_artifacts = exporter
    compact._figure_artifacts = exporter
    try:
        yield
    finally:
        canonical._figure_artifacts = old_canonical
        compact._figure_artifacts = old_compact


def _load_saved_display_records(manifest):
    if manifest.get("schema") != canonical.SCHEMA:
        raise ValueError("unsupported structure figure manifest")
    records = {}
    for key, record in manifest["input_maps"].items():
        descriptor = record["display_arrays"]
        path = Path(descriptor["path"])
        if not path.is_absolute():
            path = ROOT / path
        if canonical.file_sha256(path) != descriptor["sha256"]:
            raise ValueError(f"saved display file digest mismatch: {key}")
        with np.load(path, allow_pickle=False) as saved:
            arrays = {name: saved[name] for name in saved.files}
        if {name: canonical.array_descriptor(value) for name, value in arrays.items()} != descriptor["arrays"]:
            raise ValueError(f"saved display array digest mismatch: {key}")
        records[key] = {**record, "display": arrays}
    return records


def finalize(manifest_paths, audit_directory):
    started = time.perf_counter()
    sources = _source_hashes()
    audit_directory = Path(audit_directory).resolve()
    audit_directory.mkdir(parents=True, exist_ok=True)
    staged = []
    all_payloads = {}
    for manifest_path in manifest_paths:
        manifest_path = Path(manifest_path).resolve()
        original_payload = manifest_path.read_bytes()
        manifest = json.loads(original_payload)
        compact_case = bool(manifest.get("demonstration_variant"))
        case = "compact" if compact_case else "canonical"
        original_copy = audit_directory / f"{case}_input_generation_manifest.json"
        if original_copy.exists() and original_copy.read_bytes() != original_payload:
            raise FileExistsError("use a new audit directory for another finalization attempt")
        atomic_publish(original_copy, original_payload, _sha(original_payload))
        records = _load_saved_display_records(manifest)
        exporter = MemoryFigureExporter(compact_case=compact_case)
        with intercept_exporters(exporter):
            if compact_case:
                figures = compact._compose_family(records,
                    manifest["encoding"]["height"]["shared_limits_um"], manifest_path.parent)
            else:
                figures = canonical.compose_figures(records,
                    manifest["encoding"]["height"]["shared_limits_um"], manifest_path.parent)
        if len(figures) != 3 or len(exporter.payloads) != 9:
            raise ValueError("each accepted case must contain three figures in three formats")
        if set(all_payloads) & set(exporter.payloads):
            raise ValueError("two cases target the same output file")
        all_payloads.update(exporter.payloads)
        final_manifest = deepcopy(manifest)
        final_manifest["figures"] = figures
        final_manifest["publication_finalization"] = {
            "schema": FINALIZATION_SCHEMA,
            "source_files_sha256": sources,
            "input_generation_manifest": {"path": _path(original_copy), "sha256": _sha(original_payload)},
            "original_producer_sources_preserved": True,
            "input_map_descriptors_preserved": True,
            "geometry_retraced": False, "display_fields_recomputed": False,
            "light_transport_render_calls": 0,
            "serialization": "savefig to BytesIO; validate; atomic write with flush/fsync/replace; exact-byte readback",
            "pdf_validation_scope": "required header and terminal EOF; full page parsing is outside this finalizer; see separate QA records",
            "layout_adjustments": exporter.layout_adjustments,
            "skipped_unreferenced_intermediate": "fabric_structure_triptych for compact only" if compact_case else None,
            "actual_accepted_files": 9,
        }
        if final_manifest["input_maps"] != manifest["input_maps"] or final_manifest["producer_sources_sha256"] != manifest["producer_sources_sha256"]:
            raise RuntimeError("finalization attempted to change original map provenance")
        staged.append((case, manifest_path, final_manifest, set(exporter.payloads)))
    if _source_hashes() != sources:
        raise RuntimeError("publication code changed during composition")
    # Every figure container is complete and validated in memory before any of
    # the accepted figure paths are touched.
    for path, payload in all_payloads.items():
        atomic_publish(path, payload, _sha(payload))
    quarantined = []
    quarantine_directory = audit_directory / "unreferenced_intermediates"
    for case, manifest_path, manifest, accepted in staged:
        for path in manifest_path.parent.iterdir():
            if path.is_file() and path.suffix.lower() in (".png", ".pdf", ".svg") and path.resolve() not in accepted:
                payload = path.read_bytes()
                target = quarantine_directory / case / path.name
                atomic_publish(target, payload, _sha(payload))
                path.unlink()
                quarantined.append({"previous_path": _path(path), "quarantine_path": _path(target),
                                    "sha256": _sha(payload), "size_bytes": len(payload),
                                    "reason": "not referenced by the accepted three-family manifest"})
    # Recheck all 18 accepted paths after both cases have been published.
    final_checks = []
    for path, expected in all_payloads.items():
        actual = path.read_bytes()
        if actual != expected:
            raise RuntimeError(f"final byte-set check failed: {path}")
        final_checks.append({"path": _path(path), "sha256": _sha(actual),
                             "size_bytes": len(actual), "container": validate_container(actual, path.suffix)})
    manifests = []
    for case, path, manifest, _ in staged:
        manifest["publication_finalization"]["all_cases_post_write_byte_check_passed"] = True
        canonical.atomic_json(path, manifest)
        manifests.append({"case": case, "path": _path(path), "sha256": canonical.file_sha256(path)})
    report = {"schema": FINALIZATION_SCHEMA, "status": "passed",
        "source_files_sha256": sources, "elapsed_seconds": time.perf_counter() - started,
        "geometry_retraced": False, "accepted_figures": len(final_checks),
        "checks": final_checks, "manifests": manifests, "quarantined": quarantined}
    canonical.atomic_json(audit_directory / "publication_checks.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", help="repeat for two cases")
    parser.add_argument("--audit-directory", type=Path, default=ROOT / "data/validation_v5_1/figure_finalization")
    args = parser.parse_args(argv)
    manifests = args.manifest or [ROOT / "figures/structure_v5_1/figure_manifest.json",
                                 ROOT / "figures/structure_v5_1/compact/figure_manifest.json"]
    result = finalize(manifests, args.audit_directory)
    print(json.dumps({"status": result["status"], "accepted_figure_files": result["accepted_figures"],
                      "geometry_retraced": False, "elapsed_seconds": result["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
