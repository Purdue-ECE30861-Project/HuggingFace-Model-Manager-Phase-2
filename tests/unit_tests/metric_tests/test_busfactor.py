import unittest
import tempfile
import os
from pathlib import Path
from src.backend_server.classes.bus_factor import BusFactor, SHORTLOG_RE
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactType, ArtifactData
from src.backend_server.model.dependencies import DependencyBundle

class TestBusFactor(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.bus_factor = BusFactor(contributors_half_score_point=5)

    def test_parse_shortlog_empty(self):
        """Test parsing empty shortlog"""
        result = self.bus_factor.parse_shortlog("")
        self.assertEqual(result, {})

    def test_parse_shortlog_valid(self):
        """Test parsing valid shortlog entries"""
        shortlog = """     10\tJohn Doe
     5\tJane Smith
     2\tBob Wilson"""
        expected = {
            "John Doe": 10,
            "Jane Smith": 5,
            "Bob Wilson": 2
        }
        result = self.bus_factor.parse_shortlog(shortlog)
        self.assertEqual(result, expected)

    def test_parse_shortlog_invalid_lines(self):
        """Test parsing shortlog with invalid lines"""
        shortlog = """     10\tJohn Doe
     invalid line
     5\tJane Smith
     not a valid entry"""
        expected = {
            "John Doe": 10,
            "Jane Smith": 5
        }
        result = self.bus_factor.parse_shortlog(shortlog)
        self.assertEqual(result, expected)

    def test_shortlog_regex_matches(self):
        """Test the shortlog regex pattern with various inputs"""
        valid_cases = [
            ("     10\tJohn Doe", {"count": "10", "name": "John Doe"}),
            ("     5\tJane Smith", {"count": "5", "name": "Jane Smith"}),
            ("\t2\tBob Wilson", {"count": "2", "name": "Bob Wilson"}),
            ("  100\tUser Name", {"count": "100", "name": "User Name"})
        ]
        
        for input_line, expected in valid_cases:
            match = SHORTLOG_RE.match(input_line)
            self.assertIsNotNone(match, f"Should match: {input_line}")
            self.assertEqual(match.group(1), expected["count"])
            self.assertEqual(match.group(2), expected["name"])

    def test_shortlog_regex_non_matches(self):
        """Test the shortlog regex pattern with invalid inputs"""
        invalid_cases = [
            "Invalid",
            "Name 5",
            "",
            "    abc\tJohn Doe",
            "    10John Doe",
            "    10",
        ]
        
        for input_line in invalid_cases:
            match = SHORTLOG_RE.match(input_line)
            self.assertIsNone(match, f"Should not match: {input_line}")

    def test_calculate_bus_factor(self):
        """Test bus factor calculation with different contributor counts"""
        test_cases = [
            (0, 0, 0.0),  # No contributors
            (5, 5, 0.5),  # At half score point
            (10, 5, 0.75),  # Above half score point
            (2, 8, 0.67),  # Takes max of both numbers
            (100, 50, 0.99),  # Large number of contributors
        ]

        for gh_contributors, hf_contributors, expected_score in test_cases:
            with self.subTest(gh=gh_contributors, hf=hf_contributors):
                score = self.bus_factor.calculate_bus_factor(gh_contributors, hf_contributors)
                self.assertAlmostEqual(score, expected_score, places=1)

    def test_metric_name(self):
        """Test the metric name is correctly set"""
        self.assertEqual(self.bus_factor.metric_name, "bus_factor")

    def test_initialization(self):
        """Test initialization with different parameters"""
        test_cases = [
            (1, 0.1),
            (5, 0.2),
            (10, 0.5),
        ]

        for half_point, weight in test_cases:
            with self.subTest(half_point=half_point, weight=weight):
                bf = BusFactor(contributors_half_score_point=half_point, metric_weight=weight)
                self.assertEqual(bf.contributors_half_score_point, half_point)
                self.assertEqual(bf.metric_weight, weight)

    def test_bus_factor_bounds(self):
        """Test that bus factor scores are always between 0 and 1"""
        test_inputs = [
            (0, 0),
            (1, 1),
            (100, 200),
            (1000, 500),
            (-1, 5),  # Should handle negative numbers gracefully
        ]

        for gh_count, hf_count in test_inputs:
            score = self.bus_factor.calculate_bus_factor(gh_count, hf_count)
            self.assertGreaterEqual(score, 0.0, "Score should not be less than 0")
            self.assertLessEqual(score, 1.0, "Score should not be greater than 1")

    def test_parse_shortlog_edge_cases(self):
        """Test parsing shortlog with various edge cases"""
        edge_cases = [
            # Empty lines
            ("\n\n\n", {}),
            # Multiple tabs
            ("    10\t\tJohn Doe", {"John Doe": 10}),
            # Leading/trailing whitespace
            ("    5\tJane Smith    \n", {"Jane Smith": 5}),
            # Unicode characters
            ("    3\tJosé García", {"José García": 3}),
            # Very large numbers
            ("    999999\tBig Contributor", {"Big Contributor": 999999}),
        ]

        for input_log, expected in edge_cases:
            with self.subTest(input_log=input_log):
                result = self.bus_factor.parse_shortlog(input_log)
                self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()