import unittest
from src.backend_server.classes.size import Size
from src.contracts.artifact_contracts import SizeScore, ArtifactCost

class TestSize(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.size_metric = Size(
            rpi_max_size_mb=1000.0,    # 1GB for Raspberry Pi
            jsn_max_size_mb=2000.0,    # 2GB for Jetson Nano
            dpc_max_size_mb=5000.0,    # 5GB for Desktop PC
            aws_max_size_mb=10000.0,   # 10GB for AWS Server
            metric_weight=0.1
        )

    def test_initialization(self):
        """Test proper initialization of the Size class"""
        self.assertEqual(self.size_metric.rpi_max_size_mb, 1000.0)
        self.assertEqual(self.size_metric.jsn_max_size_mb, 2000.0)
        self.assertEqual(self.size_metric.dpc_max_size_mb, 5000.0)
        self.assertEqual(self.size_metric.aws_max_size_mb, 10000.0)
        self.assertEqual(self.size_metric.metric_weight, 0.1)
        self.assertEqual(self.size_metric.metric_name, "size_score")

    def test_calculate_size_score_with_max_size(self):
        """Test size score calculation with various sizes"""
        test_cases = [
            # (max_size, size, expected_score)
            (1000.0, 0.0, 1.0),      # Empty size
            (1000.0, 500.0, 0.5),    # Half of max size
            (1000.0, 1000.0, 0.0),   # At max size
            (1000.0, 2000.0, 0.0),   # Over max size
            (2000.0, 1000.0, 0.5),   # Different max size
            (100.0, 50.0, 0.5),      # Small numbers
            (1000.0, -100.0, 0.0),   # Negative size (edge case)
        ]

        for max_size, size, expected in test_cases:
            with self.subTest(max_size=max_size, size=size):
                score = self.size_metric.calculate_size_score_with_max_size(max_size, size)
                self.assertAlmostEqual(score, max(0.0, min(1.0, expected)), places=6)
                print(max_size, size, expected, score)

    def test_generate_score_output(self):
        """Test score generation for all platforms"""
        test_cases = [
            # (artifact_size, expected_scores)
            (0.0, [1.0, 1.0, 1.0, 1.0]),           # Empty artifact
            (500.0, [0.5, 0.75, 0.9, 0.95]),       # Small artifact
            (1500.0, [0.0, 0.25, 0.7, 0.85]),      # Medium artifact
            (8000.0, [0.0, 0.0, 0.0, 0.2]),        # Large artifact
            (15000.0, [0.0, 0.0, 0.0, 0.0]),       # Oversized artifact
        ]

        for size_mb, expected_scores in test_cases:
            with self.subTest(size_mb=size_mb):
                return_value = SizeScore(
                    raspberry_pi=0.0,
                    jetson_nano=0.0,
                    desktop_pc=0.0,
                    aws_server=0.0
                )
                artifact_size = ArtifactCost(standalone_cost=size_mb, total_cost=0)
                
                result = self.size_metric.generate_score_output(return_value, artifact_size)
                
                # Check each platform's score
                self.assertAlmostEqual(result.raspberry_pi, expected_scores[0], places=2)
                self.assertAlmostEqual(result.jetson_nano, expected_scores[1], places=2)
                self.assertAlmostEqual(result.desktop_pc, expected_scores[2], places=2)
                self.assertAlmostEqual(result.aws_server, expected_scores[3], places=2)

    def test_score_bounds(self):
        """Test that all scores are bounded between 0 and 1"""
        test_sizes = [-1000.0, 0.0, 500.0, 1000.0, 5000.0, 10000.0, 20000.0]
        
        for size in test_sizes:
            with self.subTest(size=size):
                return_value = SizeScore(
                    raspberry_pi=0.0,
                    jetson_nano=0.0,
                    desktop_pc=0.0,
                    aws_server=0.0
                )
                artifact_size = ArtifactCost(standalone_cost=size, total_cost=0)
                result = self.size_metric.generate_score_output(return_value, artifact_size)
                
                # Check bounds for all platforms
                for platform_score in [
                    result.raspberry_pi,
                    result.jetson_nano,
                    result.desktop_pc,
                    result.aws_server
                ]:
                    self.assertGreaterEqual(platform_score, 0.0)
                    self.assertLessEqual(platform_score, 1.0)

    def test_platform_ordering(self):
        """Test that platform scores are ordered correctly for same artifact size"""
        test_sizes = [100.0, 1000.0, 2000.0, 5000.0, 8000.0]
        
        for size in test_sizes:
            with self.subTest(size=size):
                return_value = SizeScore(
                    raspberry_pi=0.0,
                    jetson_nano=0.0,
                    desktop_pc=0.0,
                    aws_server=0.0
                )
                artifact_size = ArtifactCost(standalone_cost=size, total_cost=0)
                result = self.size_metric.generate_score_output(return_value, artifact_size)
                
                # Check that scores are ordered by platform capacity
                scores = [
                    result.raspberry_pi,
                    result.jetson_nano,
                    result.desktop_pc,
                    result.aws_server
                ]
                self.assertEqual(scores, sorted(scores))  # Should be in ascending order

    def test_edge_cases(self):
        """Test edge cases for size calculations"""
        edge_cases = [
            (0.0, "zero_size"),
            (float('inf'), "infinite_size"),
            (-1.0, "negative_size")
        ]
        
        for size, case_name in edge_cases:
            with self.subTest(case=case_name):
                return_value = SizeScore(
                    raspberry_pi=0.0,
                    jetson_nano=0.0,
                    desktop_pc=0.0,
                    aws_server=0.0
                )
                artifact_size = ArtifactCost(standalone_cost=size, total_cost=0)
                result = self.size_metric.generate_score_output(return_value, artifact_size)
                
                # Check that all scores are valid
                for platform_score in [
                    result.raspberry_pi,
                    result.jetson_nano,
                    result.desktop_pc,
                    result.aws_server
                ]:
                    self.assertGreaterEqual(platform_score, 0.0)
                    self.assertLessEqual(platform_score, 1.0)
                    self.assertFalse(isinstance(platform_score, complex))

if __name__ == '__main__':
    unittest.main()