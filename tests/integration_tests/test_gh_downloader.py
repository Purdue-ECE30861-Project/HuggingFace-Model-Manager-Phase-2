import tempfile
import unittest
from pathlib import Path
from src.backend_server.model.data_store.downloaders.gh_downloader import GHArtifactDownloader
from src.contracts.artifact_contracts import ArtifactType


class TestGHArtifactDownloader(unittest.TestCase):
    def setUp(self):
        self.downloader = GHArtifactDownloader(timeout=10)
        self.valid_github_url = "https://github.com/user123/repo456"
        self.valid_github_url_with_git = "https://github.com/user123/repo456.git"
        self.valid_github_url_http = "http://github.com/user123/repo456"
        self.invalid_url = "https://example.com/not-github"
        self.invalid_hf_url = "https://huggingface.co/user123/model456"

    def test_validate_url(self):
        """Ensure _validate_url correctly identifies GitHub URLs"""
        self.assertTrue(self.downloader._validate_url(self.valid_github_url))
        self.assertTrue(self.downloader._validate_url(self.valid_github_url_with_git))
        self.assertTrue(self.downloader._validate_url(self.valid_github_url_http))
        self.assertFalse(self.downloader._validate_url(self.invalid_url))
        self.assertFalse(self.downloader._validate_url(self.invalid_hf_url))

    def test_get_repo_id_from_url_code(self):
        """Check repo ID extraction for code URLs"""
        repo_id = self.downloader._get_repo_id_from_url(self.valid_github_url, ArtifactType.code)
        self.assertEqual(repo_id, "user123/repo456")
        
        # Test with .git suffix
        repo_id_git = self.downloader._get_repo_id_from_url(self.valid_github_url_with_git, ArtifactType.code)
        self.assertEqual(repo_id_git, "user123/repo456")
        
        # Test with http
        repo_id_http = self.downloader._get_repo_id_from_url(self.valid_github_url_http, ArtifactType.code)
        self.assertEqual(repo_id_http, "user123/repo456")

    def test_get_repo_id_from_url_invalid(self):
        """Ensure invalid URLs raise proper error"""
        with self.assertRaises(NameError):
            self.downloader._get_repo_id_from_url("https://github.com/onlyowner", ArtifactType.code)
        
        with self.assertRaises(NameError):
            self.downloader._get_repo_id_from_url("https://github.com/", ArtifactType.code)

    def test_get_repo_id_from_url_model(self):
        """Ensure invalid type for model raises proper error"""
        with self.assertRaises(TypeError):
            self.downloader._get_repo_id_from_url(self.valid_github_url, ArtifactType.model)

    def test_get_repo_id_from_url_dataset(self):
        """Ensure invalid type for dataset raises proper error"""
        with self.assertRaises(TypeError):
            self.downloader._get_repo_id_from_url(self.valid_github_url, ArtifactType.dataset)

    def test_download_artifact_integration(self):
        """Integration test: download a small GitHub repo, check contents and size."""
        # Use a small, public repository for testing (e.g., a simple test repo)
        # Using a well-known small repo like 'octocat/Hello-World' or a test repo
        repo_url = "https://github.com/octocat/Hello-World"
        artifact_type = ArtifactType.code

        with tempfile.TemporaryDirectory() as tempdir_obj:
            size = self.downloader.download_artifact(repo_url, artifact_type, Path(tempdir_obj))
            self.assertIsNotNone(tempdir_obj)
            self.assertGreater(size, 0, "Downloaded size should be > 0")

            # Check that downloaded folder has files
            download_path = Path(tempdir_obj)
            files = list(download_path.rglob("*"))
            # Filter out .git directory
            files = [f for f in files if '.git' not in str(f)]
            self.assertTrue(len(files) > 0, f"No files found in downloaded folder {download_path}")

            # Check for common repository files (README, LICENSE, etc.)
            found = False
            for f in files:
                if f.is_file() and f.name.lower() in ("readme", "readme.md", "license", "license.txt", ".gitignore"):
                    found = True
                    break
            # At minimum, there should be some files in the repo
            self.assertTrue(found or len([f for f in files if f.is_file()]) > 0, 
                          f"Expected repository files not found in {download_path}")

            # Check size corresponds roughly to sum of file sizes (excluding .git)
            computed_size = sum(f.stat().st_size for f in files if f.is_file())
            # Allow some tolerance since we're excluding .git directory
            self.assertLess(abs(size - computed_size), 10000, 
                          "Reported size should be close to sum of file sizes (excluding .git)")

    def test_download_artifact_nonexistent_repo(self):
        """Test that downloading a non-existent repository raises FileNotFoundError"""
        fake_url = "https://github.com/nonexistentuser/definitelydoesnotexist12345"
        artifact_type = ArtifactType.code

        with tempfile.TemporaryDirectory() as tempdir_obj:
            with self.assertRaises(FileNotFoundError):
                self.downloader.download_artifact(fake_url, artifact_type, Path(tempdir_obj))

    def test_download_artifact_with_subdirectory(self):
        """Test that URLs with subdirectories still extract repo correctly"""
        url_with_path = "https://github.com/user123/repo456/tree/main/src"
        repo_id = self.downloader._get_repo_id_from_url(url_with_path, ArtifactType.code)
        self.assertEqual(repo_id, "user123/repo456")

if __name__ == "__main__":
    unittest.main()
