import unittest
from pathlib import Path
from src.backend_server.classes.dataset_quality import DatasetQuality
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactType, ArtifactData
from src.backend_server.model.dependencies import DependencyBundle

class TestDatasetQuality(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.dataset_quality = DatasetQuality(
            half_score_point_likes=100,
            half_score_point_downloads=1000,
            half_score_point_dimensions=3,
            metric_weight=0.1
        )

    def test_initialization(self):
        """Test proper initialization of the DatasetQuality class"""
        self.assertEqual(self.dataset_quality.half_score_point_likes, 100)
        self.assertEqual(self.dataset_quality.half_score_point_downloads, 1000)
        self.assertEqual(self.dataset_quality.half_score_point_dimensions, 3)
        self.assertEqual(self.dataset_quality.metric_weight, 0.1)
        self.assertEqual(self.dataset_quality.metric_name, "dataset_quality")

    def test_determine_dataset_quality_zero_values(self):
        """Test quality determination with zero values"""
        score = self.dataset_quality.determine_dataset_quality(
            num_likes=0,
            num_downloads=0,
            num_dimensions=0
        )
        self.assertEqual(score, 0.0)

    def test_determine_dataset_quality_at_half_points(self):
        """Test quality determination at half score points"""
        score = self.dataset_quality.determine_dataset_quality(
            num_likes=100,  # half score point for likes
            num_downloads=1000,  # half score point for downloads
            num_dimensions=3  # half score point for dimensions
        )
        # Each component should be 0.5, average should be 0.5
        self.assertAlmostEqual(score, 0.5, places=2)

    def test_determine_dataset_quality_above_half_points(self):
        """Test quality determination above half score points"""
        score = self.dataset_quality.determine_dataset_quality(
            num_likes=200,  # double half score point
            num_downloads=2000,  # double half score point
            num_dimensions=6  # double half score point
        )
        self.assertGreater(score, 0.5)
        self.assertLessEqual(score, 1.0)

    def test_determine_dataset_quality_mixed_values(self):
        """Test quality determination with mixed values"""
        test_cases = [
            (50, 500, 2),    # Below half points
            (150, 1500, 4),  # Above half points
            (100, 2000, 1),  # Mixed values
            (1000, 0, 10),   # Extreme mixed values
        ]

        for likes, downloads, dimensions in test_cases:
            with self.subTest(likes=likes, downloads=downloads, dimensions=dimensions):
                score = self.dataset_quality.determine_dataset_quality(likes, downloads, dimensions)
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)

    def test_determine_dataset_quality_large_values(self):
        """Test quality determination with very large values"""
        score = self.dataset_quality.determine_dataset_quality(
            num_likes=10000,
            num_downloads=100000,
            num_dimensions=100
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertGreater(score, 0.5)  # Should be high quality

    def test_determine_dataset_quality_negative_values(self):
        """Test quality determination with negative values (edge case)"""
        score = self.dataset_quality.determine_dataset_quality(
            num_likes=-1,
            num_downloads=-100,
            num_dimensions=-5
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_different_half_score_points(self):
        """Test with different half score point configurations"""
        test_configs = [
            (10, 100, 2),     # Lower half points
            (1000, 10000, 10), # Higher half points
            (50, 5000, 5),     # Mixed half points
        ]

        for likes_half, downloads_half, dimensions_half in test_configs:
            with self.subTest(likes_half=likes_half, downloads_half=downloads_half, 
                            dimensions_half=dimensions_half):
                dq = DatasetQuality(
                    half_score_point_likes=likes_half,
                    half_score_point_downloads=downloads_half,
                    half_score_point_dimensions=dimensions_half
                )
                
                # Test at half points
                score = dq.determine_dataset_quality(
                    num_likes=likes_half,
                    num_downloads=downloads_half,
                    num_dimensions=dimensions_half
                )
                self.assertAlmostEqual(score, 0.5, places=2)

    def test_score_component_weights(self):
        """Test that all components contribute equally to the final score"""
        # Test with perfect scores for each component individually
        likes_only = self.dataset_quality.determine_dataset_quality(10000, 0, 0)
        downloads_only = self.dataset_quality.determine_dataset_quality(0, 100000, 0)
        dimensions_only = self.dataset_quality.determine_dataset_quality(0, 0, 100)

        # Each component should contribute approximately 1/3 when maxed out
        self.assertAlmostEqual(likes_only, 1/3, places=1)
        self.assertAlmostEqual(downloads_only, 1/3, places=1)
        self.assertAlmostEqual(dimensions_only, 1/3, places=1)

if __name__ == '__main__':
    unittest.main()