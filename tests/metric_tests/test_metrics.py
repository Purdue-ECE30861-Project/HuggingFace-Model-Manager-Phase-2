# tests/test_metrics.py
import unittest
from src.classes.Metric import Metric

class DummyMetric(Metric):
    """Tiny concrete subclass so we don't pull in any heavy deps."""
    def __init__(self, metricName="Dummy", metricScore=0.0, metricWeighting=0.1):
        super().__init__(metricName, metricScore, metricWeighting)

class TestMetricBase(unittest.TestCase):
    def test_defaults(self):
        m = DummyMetric()
        self.assertEqual(m.getMetricName(), "Dummy")
        self.assertEqual(m.getMetricScore(), 0.0)
        self.assertEqual(m.getWeighting(), 0.1)
        self.assertEqual(m.getLatency(), 0)

    def test_custom_init_values(self):
        m = DummyMetric(metricName="Quality", metricScore=0.75, metricWeighting=0.2)
        self.assertEqual(m.getMetricName(), "Quality")
        self.assertEqual(m.getMetricScore(), 0.75)
        self.assertEqual(m.getWeighting(), 0.2)

    def test_latency_is_mutable_int(self):
        m = DummyMetric()
        m.metricLatency = 123  # simulate a measured latency
        self.assertIsInstance(m.getLatency(), int)
        self.assertEqual(m.getLatency(), 123)

    def test_score_and_weight_are_floats(self):
        m = DummyMetric(metricScore=1.0, metricWeighting=0.33)
        self.assertIsInstance(m.getMetricScore(), float)
        self.assertIsInstance(m.getWeighting(), float)
        self.assertGreaterEqual(m.getMetricScore(), 0.0)
        self.assertLessEqual(m.getMetricScore(), 1.0)
        self.assertGreaterEqual(m.getWeighting(), 0.0)
        self.assertLessEqual(m.getWeighting(), 1.0)

if __name__ == "__main__":
    unittest.main()