import unittest
import math

from src.backend_server.classes.get_exp_coefficient import (
    get_exp_coefficient,
    score_large_good,
    score_large_bad
)

class TestExponentialScoring(unittest.TestCase):
    def test_get_exp_coefficient(self):
        """Test the exponential coefficient calculation"""
        # Test with different half magnitude points
        test_cases = [
            (1.0, math.log2(0.5)),  # Should equal log2(0.5)
            (2.0, math.log2(0.5)/2),  # Should be half of log2(0.5)
            (4.0, math.log2(0.5)/4),  # Should be quarter of log2(0.5)
            (0.5, math.log2(0.5)/0.5),  # Should be double of log2(0.5)
        ]
        
        for half_point, expected in test_cases:
            with self.subTest(half_point=half_point):
                result = get_exp_coefficient(half_point)
                self.assertAlmostEqual(result, expected, places=10)
                
        # Test error cases
        with self.assertRaises(ZeroDivisionError):
            get_exp_coefficient(0)
            
    def test_score_large_good(self):
        """Test scoring function that approaches 1 as score increases"""
        # Get coefficient for testing
        coef = get_exp_coefficient(2.0)
        
        test_cases = [
            (0.0, 0.0),  # Zero score should give zero
            (float('inf'), 1.0),  # Infinite score should approach 1
            (2.0, 0.5),  # At half magnitude point should give 0.5
        ]
        
        for score, expected in test_cases:
            with self.subTest(score=score):
                result = score_large_good(coef, score)
                self.assertAlmostEqual(result, expected, places=10)
                
        # Test monotonic increase
        scores = [0, 1, 2, 4, 8, 16]
        results = [score_large_good(coef, score) for score in scores]
        for i in range(len(results)-1):
            self.assertLess(results[i], results[i+1])
            
        # Test bounds
        for score in [-1000, -1, 0, 1, 1000]:
            result = score_large_good(coef, score)
            self.assertGreaterEqual(result, 0.0)
            self.assertLessEqual(result, 1.0)
            
    def test_score_large_bad(self):
        """Test scoring function that approaches 0 as score increases"""
        # Get coefficient for testing
        coef = get_exp_coefficient(2.0)
        
        test_cases = [
            (0.0, 1.0),  # Zero score should give one
            (float('inf'), 0.0),  # Infinite score should approach 0
            (2.0, 0.5),  # At half magnitude point should give 0.5
        ]
        
        for score, expected in test_cases:
            with self.subTest(score=score):
                result = score_large_bad(coef, score)
                self.assertAlmostEqual(result, expected, places=10)
                
        # Test monotonic decrease
        scores = [0, 1, 2, 4, 8, 16]
        results = [score_large_bad(coef, score) for score in scores]
        for i in range(len(results)-1):
            self.assertGreater(results[i], results[i+1])
            
        # Test bounds
        for score in [-1000, -1, 0, 1, 1000]:
            result = score_large_bad(coef, score)
            self.assertGreaterEqual(result, 0.0)
            self.assertLessEqual(result, 1.0)
            
    def test_complementary_relationship(self):
        """Test that good and bad scoring are complementary"""
        coef = get_exp_coefficient(2.0)
        test_scores = [0, 1, 2, 3, 4, 5]
        
        for score in test_scores:
            with self.subTest(score=score):
                good_score = score_large_good(coef, score)
                bad_score = score_large_bad(coef, score)
                self.assertAlmostEqual(good_score + bad_score, 1.0, places=10)
                
    def test_half_point_accuracy(self):
        """Test that scores are exactly 0.5 at the half magnitude point"""
        half_points = [1.0, 2.0, 4.0, 8.0]
        
        for half_point in half_points:
            with self.subTest(half_point=half_point):
                coef = get_exp_coefficient(half_point)
                
                # Test good scoring
                good_score = score_large_good(coef, half_point)
                self.assertAlmostEqual(good_score, 0.5, places=10)
                
                # Test bad scoring
                bad_score = score_large_bad(coef, half_point)
                self.assertAlmostEqual(bad_score, 0.5, places=10)

if __name__ == '__main__':
    unittest.main()