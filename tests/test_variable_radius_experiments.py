"""Regression tests for an observed incomplete experiment archive."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np

from run_variable_radius_experiments import save_npz_atomic, validate_saved_arrays, write_json


class ExperimentArchiveIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def fixture(self):
        path = self.root/"renderer_buffers.npz"
        values = np.arange(360, dtype=np.float32).reshape(120, 3)
        save_npz_atomic(path, vertices=values)
        meta = self.root/"mesh_manifest.json"
        write_json(meta, {"arrays_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return path, meta, values

    def test_complete_archive_round_trip_and_nested_integrity(self):
        path, _, values = self.fixture()
        with np.load(path, allow_pickle=False) as archive:
            np.testing.assert_array_equal(archive["vertices"], values)
            self.assertEqual(archive["vertices"].dtype, np.float32)
        result = validate_saved_arrays(self.root)
        self.assertEqual(result["npz_count"], 1)
        self.assertEqual(result["nested_array_reference_count"], 1)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ["mesh_manifest.json", "renderer_buffers.npz"])

    def test_missing_zip_directory_rejected_even_with_fresh_outer_hash(self):
        path, _, _ = self.fixture()
        raw = path.read_bytes()
        directory = raw.index(b"PK\x01\x02")
        path.write_bytes(raw[:directory])
        write_json(self.root/"experiment_manifest.json",
                   {"output_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}})
        with self.assertRaises(zipfile.BadZipFile):
            validate_saved_arrays(self.root)

    def test_valid_replacement_archive_does_not_bypass_inner_hash(self):
        path, _, values = self.fixture()
        save_npz_atomic(path, vertices=values+1)
        with self.assertRaisesRegex(OSError, "nested array checksum mismatch"):
            validate_saved_arrays(self.root)

    def test_unreferenced_archive_rejected(self):
        _, meta, _ = self.fixture()
        meta.unlink()
        with self.assertRaisesRegex(OSError, "no independently recorded"):
            validate_saved_arrays(self.root)

    def test_profile_and_optics_references_are_both_checked(self):
        profiles = self.root/"profiles"
        profiles.mkdir()
        optical = self.root/"optics"
        optical.mkdir()
        for folder, file, label in ((profiles, "profile.npz", "profile"),
                                     (optical, "spectral_radiance.npz", "optics")):
            save_npz_atomic(folder/file, scalar=np.ones((2, 2), dtype=np.float32))
            digest = hashlib.sha256((folder/file).read_bytes()).hexdigest()
            info = ({"array_file": file, "array_file_sha256": digest} if label == "profile"
                    else {"spectral_radiance_sha256": digest})
            write_json(folder/("variable_radius_profiles.json" if label == "profile"
                                else "optical_metrics.json"), info)
        self.assertEqual(validate_saved_arrays(self.root)["npz_count"], 2)
        info = json.loads((optical/"optical_metrics.json").read_text())
        info["spectral_radiance_sha256"] = "0"*64
        write_json(optical/"optical_metrics.json", info)
        with self.assertRaisesRegex(OSError, "nested array checksum mismatch"):
            validate_saved_arrays(self.root)


if __name__ == "__main__":
    unittest.main()
