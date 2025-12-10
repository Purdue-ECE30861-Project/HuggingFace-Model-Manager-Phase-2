import unittest
import tempfile
import shutil
from pathlib import Path
import git
from src.backend_server.classes.code_quality import CodeQuality
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
from src.backend_server.model.dependencies import DependencyBundle

# Constants for testing
GH_URL = "https://github.com/MalinkyZubr/QuineMcKluskey.git"

class TestCodeQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up a temporary directory and clone the test repository."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.repo_path = Path(cls.temp_dir) / "repo"
        
        # Clone the repository
        print(f"Cloning repository to {cls.repo_path}...")
        git.Repo.clone_from(GH_URL, cls.repo_path)
        
        # Create test artifacts and dependencies
        cls.artifact = Artifact(
            metadata=ArtifactMetadata(
                name="test-repo",
                id="test-id",
                type=ArtifactType.code
            ),
            data=ArtifactData(
                url=GH_URL,
                download_url=""
            )
        )
        
        # Create an empty DependencyBundle for testing
        cls.dependencies = DependencyBundle(s3=None, db=None, llm_accessor=None)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary directory after tests."""
        shutil.rmtree(cls.temp_dir)

    def setUp(self):
        """Set up for each test."""
        self.code_quality = CodeQuality()

    def test_calculate_metric_score_with_valid_repo(self):
        """Test calculating metric score with a valid repository."""
        score = self.code_quality.calculate_metric_score(
            self.repo_path,
            self.artifact,
            self.dependencies
        )
        
        # Score should be between 0 and 1
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        print(f"Repository received a code quality score of: {score}")

    def test_calculate_metric_score_invalid_path(self):
        """Test calculating metric score with an invalid path."""
        invalid_path = Path(self.temp_dir) / "nonexistent"
        
        with self.assertRaises(ValueError) as context:
            self.code_quality.calculate_metric_score(
                invalid_path,
                self.artifact,
                self.dependencies
            )
        
        self.assertIn("Path does not exist", str(context.exception))

    def test_metric_name(self):
        """Test the metric name is correctly set."""
        self.assertEqual(self.code_quality.metric_name, "code_quality")

    def test_score_normalization(self):
        """Test score normalization with different pylint scores."""
        # Create a mock repository with a simple Python file
        test_repo_path = Path(self.temp_dir) / "test_repo"
        test_repo_path.mkdir(exist_ok=True)
        
        # Create a test Python file with different quality levels
        test_files = {
            "good_code.py": """
def add(a: int, b: int) -> int:
    \"\"\"Add two numbers.
    
    Args:
        a: First number
        b: Second number
    
    Returns:
        Sum of the two numbers
    \"\"\"
    return a + b
""",
            "bad_code.py": """
def f(x,y):
    z=x+y;return z
"""
        }
        
        for filename, content in test_files.items():
            file_path = test_repo_path / filename
            with open(file_path, 'w') as f:
                f.write(content)
        
        # Test each file
        for filename in test_files:
            score = self.code_quality.calculate_metric_score(
                test_repo_path / filename,
                self.artifact,
                self.dependencies
            )
            
            # Score should be normalized between 0 and 1
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            print(f"File {filename} received a code quality score of: {score}")

    def test_empty_directory(self):
        """Test handling of an empty directory."""
        empty_dir = Path(self.temp_dir) / "empty"
        empty_dir.mkdir(exist_ok=True)
        
        # Create an empty Python file to test
        empty_file = empty_dir / "empty.py"
        empty_file.touch()
        
        score = self.code_quality.calculate_metric_score(
            empty_file,
            self.artifact,
            self.dependencies
        )
        
        # Score should still be normalized between 0 and 1
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        print(f"Empty file received a code quality score of: {score}")

if __name__ == '__main__':
    unittest.main()