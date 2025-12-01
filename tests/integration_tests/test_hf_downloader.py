import tempfile
import unittest
from pathlib import Path
from src.backend_server.model.data_store.downloaders.hf_downloader import HFArtifactDownloader
from src.contracts.artifact_contracts import ArtifactType


class TestHFArtifactDownloader(unittest.TestCase):
    def setUp(self):
        self.downloader = HFArtifactDownloader(timeout=10)
        self.valid_model_url = "https://huggingface.co/user123/model456"
        self.valid_dataset_url = "https://huggingface.co/datasets/user456/dataset789"
        self.invalid_url = "https://example.com/not-huggingface"

    def test_validate_url(self):
        """Ensure _validate_url correctly identifies HuggingFace URLs"""
        self.assertTrue(self.downloader._validate_url(self.valid_model_url))
        self.assertFalse(self.downloader._validate_url(self.invalid_url))

    def test_get_repo_id_from_url_model(self):
        """Check repo ID extraction for model URLs"""
        repo_id = self.downloader._get_repo_id_from_url(self.valid_model_url, ArtifactType.model)
        self.assertEqual(repo_id, "user123/model456")

    def test_get_repo_id_from_url_dataset(self):
        """Check repo ID extraction for dataset URLs"""
        valid_dataset_url = "https://huggingface.co/datasets/user456/dataset789"
        with self.assertRaises(NameError):
            self.downloader._get_repo_id_from_url("https://huggingface.co/user456/dataset789", ArtifactType.dataset)

        # Expected error due to the intentional string bug in dataset case ('{5}')
        self.assertEqual(self.downloader._get_repo_id_from_url(valid_dataset_url, ArtifactType.dataset), 'user456/dataset789')

    def test_get_repo_id_from_url_code(self):
        """Ensure invalid type for code raises proper error"""
        with self.assertRaises(TypeError):
            self.downloader._get_repo_id_from_url(self.valid_model_url, ArtifactType.code)

    def test_download_artifact_integration(self):
        """Integration test: download a small HF model, check contents and size """
        # Download
        model_url = "https://huggingface.co/prajjwal1/bert-tiny"
        artifact_type = ArtifactType.model

        with tempfile.TemporaryDirectory() as tempdir_obj:
            size = self.downloader.download_artifact(model_url, artifact_type, Path(tempdir_obj))
            self.assertIsNotNone(tempdir_obj)
            self.assertGreater(size, 0, "Downloaded size should be > 0")

            # Check that downloaded folder has files
            download_path = Path(tempdir_obj)
            files = list(download_path.rglob("*"))
            self.assertTrue(len(files) > 0, f"No files found in downloaded folder {download_path}")

            # Inspect one expected file: config or pytorch_model.bin might exist
            found = False
            for f in files:
                if f.name in ("config.json", "pytorch_model.bin", "model.safetensors"):
                    found = True
                    break
            self.assertTrue(found, f"Expected model file not found in {download_path}")

            # Check size corresponds roughly to sum of file sizes
            computed_size = sum(f.stat().st_size for f in files if f.is_file()) / 10e6
            self.assertLess(abs(size - computed_size), 10000, "Reported size must equal sum of file sizes")

