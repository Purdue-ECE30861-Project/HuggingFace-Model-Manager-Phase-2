import unittest
import tempfile
import os
from pathlib import Path
import shutil
from src.backend_server.classes.ramp_up_time import RampUpTime, has_any


def print_tree(root, prefix=""):
    for i, name in enumerate(sorted(os.listdir(root))):
        path = os.path.join(root, name)
        connector = "└── " if i == len(os.listdir(root)) - 1 else "├── "
        print(prefix + connector + name)
        if os.path.isdir(path):
            extension = "    " if i == len(os.listdir(root)) - 1 else "│   "
            print_tree(path, prefix + extension)


class TestRampUpTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures with a temporary directory structure"""
        cls.base_dir = tempfile.mkdtemp()
        cls.ramp_up = RampUpTime(
            directory_breadth_half_score_point=5,
            directory_depth_half_score_point=3,
            arxiv_link_half_score_point=2,
            num_spaces_half_score_point=1
        )
        
        # Create test directory structure
        cls.test_structure = {
            'src': {
                'main.py': 'print("Hello")',
                'utils': {
                    'helper.py': 'def help(): pass'
                }
            },
            'tests': {
                'test_main.py': 'def test_something(): pass'
            },
            'docs': {
                'README.md': '# Project\nThis is a test project\nTo install: pip install package',
                'paper.txt': 'See our paper at https://arxiv.org/abs/2301.12345'
            },
            'examples': {
                'demo.py': 'print("Demo")'
            }
        }
        
        cls._create_directory_structure(cls.base_dir, cls.test_structure)

    @classmethod
    def _create_directory_structure(cls, base_path: str, structure: dict):
        """Helper to create nested directory structure"""
        for name, content in structure.items():
            path = os.path.join(base_path, name)
            if isinstance(content, dict):
                os.makedirs(path, exist_ok=True)
                cls._create_directory_structure(path, content)
            else:
                with open(path, 'w') as f:
                    f.write(content)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary directory"""
        shutil.rmtree(cls.base_dir)

    def test_directory_depth_calculation(self):
        """Test directory depth calculation"""
        # src/utils is depth 2
        print_tree(self.base_dir)
        depth = self.ramp_up.directory_depth_calculation(Path(self.base_dir), 0)
        self.assertEqual(depth, 2)  # Maximum depth should be 2

        # Test empty directory
        with tempfile.TemporaryDirectory() as empty_dir:
            try:
                depth = self.ramp_up.directory_depth_calculation(Path(empty_dir), 0)
                self.assertEqual(depth, 0)
            finally:
                shutil.rmtree(empty_dir)

    def test_directory_size_calculation(self):
        """Test directory size calculation"""
        size_score = self.ramp_up.directory_size_calculation(Path(self.base_dir))
        self.assertGreaterEqual(size_score, 0.0)
        self.assertLessEqual(size_score, 1.0)

    def test_directory_check_arxiv_links(self):
        """Test arxiv link detection"""
        arxiv_score = self.ramp_up.directory_check_arxiv_links(Path(self.base_dir))
        self.assertGreaterEqual(arxiv_score, 0.0)
        self.assertLessEqual(arxiv_score, 1.0)

        # Test with different arxiv link formats
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, 'test.txt'), 'w') as f:
                f.write("""
                    https://arxiv.org/abs/2301.12345
                    https://arxiv.org/pdf/2301.12345.pdf
                    arXiv:2301.12345
                """)
            score = self.ramp_up.directory_check_arxiv_links(Path(test_dir))
            self.assertGreater(score, 0.0)
        finally:
            shutil.rmtree(test_dir)

    def test_directory_check_structure(self):
        """Test directory structure checking"""
        structure_score = self.ramp_up.directory_check_structure(Path(self.base_dir))
        # We have src, tests, docs, examples = 4 out of 8 possible directories
        self.assertEqual(structure_score, 0.5)

        # Test with empty directory
        empty_dir = tempfile.mkdtemp()
        try:
            score = self.ramp_up.directory_check_structure(Path(empty_dir))
            self.assertEqual(score, 0.0)
        finally:
            shutil.rmtree(empty_dir)

    def test_detect_install_instructions(self):
        """Test installation instructions detection"""
        # Test specific install instructions
        score = self.ramp_up.detect_install_instructions(Path(self.base_dir))
        self.assertEqual(score, 1.0)  # Should find "pip install" in README.md

        # Test generic install mention
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, 'README.md'), 'w') as f:
                f.write("To use this package, install it first.")
            score = self.ramp_up.detect_install_instructions(Path(test_dir))
            self.assertEqual(score, 0.5)
        finally:
            shutil.rmtree(test_dir)

        # Test no install instructions
        test_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(test_dir, 'README.md'), 'w') as f:
                f.write("This is a test package.")
            score = self.ramp_up.detect_install_instructions(Path(test_dir))
            self.assertEqual(score, 0.0)
        finally:
            shutil.rmtree(test_dir)

    def test_num_spaces_score(self):
        """Test num_spaces_score calculation"""
        scores = [
            (0, self.ramp_up.num_spaces_score(0)),
            (1, self.ramp_up.num_spaces_score(1)),
            (5, self.ramp_up.num_spaces_score(5))
        ]
        
        for num_spaces, score in scores:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            if num_spaces > 0:
                self.assertGreater(score, scores[0][1])  # Should be better than zero spaces

    def test_has_any_helper(self):
        """Test the has_any helper function"""
        # Test existing directory
        self.assertTrue(has_any(self.base_dir, ["src"]))
        self.assertTrue(has_any(self.base_dir, ["nonexistent", "src"]))
        
        # Test non-existent directory
        self.assertFalse(has_any(self.base_dir, ["nonexistent"]))
        
        # Test empty directory list
        self.assertFalse(has_any(self.base_dir, []))

if __name__ == '__main__':
    unittest.main()