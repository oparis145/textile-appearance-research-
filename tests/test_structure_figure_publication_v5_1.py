"""Container truncation and publication-boundary oracles, without geometry tracing."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

import matplotlib.pyplot as plt

from visualization import render_structure_figures as original
from visualization import render_compact_structure_figure as compact
from visualization.finalize_structure_figures import (
    atomic_publish, intercept_exporters, validate_container,
)


class FigurePublicationTests(unittest.TestCase):
    def test_three_real_formats_reject_truncation(self):
        figure, axes = plt.subplots(figsize=(1, 1))
        axes.plot([0, 1], [0, 1])
        try:
            for suffix in ("png", "pdf", "svg"):
                with self.subTest(format=suffix):
                    stream = io.BytesIO()
                    figure.savefig(stream, format=suffix, dpi=40)
                    payload = stream.getvalue()
                    self.assertEqual(validate_container(payload, suffix)["format"], suffix)
                    with self.assertRaises(ValueError):
                        validate_container(payload[:len(payload) // 2], suffix)
        finally:
            plt.close(figure)

    def test_digest_mismatch_cannot_replace_existing_destination(self):
        folder = Path(__file__).resolve().parents[1] / "scratch_runs"
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            path = Path(directory) / "artifact.bin"
            old, new = b"original accepted bytes", b"new verified bytes"
            atomic_publish(path, old, hashlib.sha256(old).hexdigest())
            with self.assertRaises(ValueError):
                atomic_publish(path, new, hashlib.sha256(old).hexdigest())
            self.assertEqual(path.read_bytes(), old)
            atomic_publish(path, new, hashlib.sha256(new).hexdigest())
            self.assertEqual(path.read_bytes(), new)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_frozen_exporters_are_restored_after_failed_composition(self):
        before = original._figure_artifacts, compact._figure_artifacts
        sentinel = object()
        with self.assertRaisesRegex(RuntimeError, "oracle"):
            with intercept_exporters(sentinel):
                self.assertIs(original._figure_artifacts, sentinel)
                self.assertIs(compact._figure_artifacts, sentinel)
                raise RuntimeError("oracle")
        self.assertIs(original._figure_artifacts, before[0])
        self.assertIs(compact._figure_artifacts, before[1])


if __name__ == "__main__":
    unittest.main()
