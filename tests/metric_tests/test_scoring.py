import io
import json
import unittest
from unittest.mock import MagicMock, patch

from src.classes.ScoreCard import ScoreCard


class TestScoreCard(unittest.TestCase):
    @patch("backend_server.classes.ScoreCard.get_github_readme", return_value="# README")
    @patch("backend_server.classes.ScoreCard.AvailableDatasetAndCode")
    @patch("backend_server.classes.ScoreCard.CodeQuality")
    @patch("backend_server.classes.ScoreCard.PerformanceClaims")
    @patch("backend_server.classes.ScoreCard.RampUpTime")
    @patch("backend_server.classes.ScoreCard.License")
    @patch("backend_server.classes.ScoreCard.Size")
    @patch("backend_server.classes.ScoreCard.DatasetQuality")
    @patch("backend_server.classes.ScoreCard.BusFactor")
    def test_total_score_aggregates_metrics(
        self,
        mock_bus_factor,
        mock_dataset_quality,
        mock_size,
        mock_license,
        mock_ramp_up,
        mock_performance,
        mock_code_quality,
        mock_availability,
        _mock_readme,
    ):
        url = "https://huggingface.co/org/model"

        bus = MagicMock(metricScore=0.8, metricLatency=4)
        bus.getMetricScore.return_value = 0.8
        bus.getWeighting.return_value = 0.1
        bus.getLatency.return_value = 4
        mock_bus_factor.return_value = bus

        dataset = MagicMock(metricScore=0.6, metricLatency=5)
        dataset.computeDatasetQuality.return_value = (0.6, 5)
        dataset.getMetricScore.return_value = 0.6
        dataset.getWeighting.return_value = 0.1
        dataset.getLatency.return_value = 5
        mock_dataset_quality.return_value = dataset

        size = MagicMock(metricScore=0.7, metricLatency=3, device_dict={"cpu": 0.7})
        size.getMetricScore.return_value = 0.7
        size.getWeighting.return_value = 0.1
        size.getLatency.return_value = 3

        def _size_side_effect(_url):
            size.metricScore = 0.7
            size.metricLatency = 3

        size.setSize.side_effect = _size_side_effect
        mock_size.return_value = size

        license_metric = MagicMock(metricScore=0.9, metricLatency=2)
        license_metric.evaluate.return_value = (0.9, 2)
        license_metric.getMetricScore.return_value = 0.9
        license_metric.getWeighting.return_value = 0.1
        license_metric.getLatency.return_value = 2
        mock_license.return_value = license_metric

        ramp = MagicMock(metricScore=1.0, metricLatency=1)
        ramp.getMetricScore.return_value = 1.0
        ramp.getWeighting.return_value = 0.2
        ramp.getLatency.return_value = 1
        mock_ramp_up.return_value = ramp

        perf = MagicMock(metricScore=0.75, metricLatency=6)
        perf.evaluate.return_value = (0.75, 6)
        perf.getMetricScore.return_value = 0.75
        perf.getWeighting.return_value = 0.1
        perf.getLatency.return_value = 6
        mock_performance.return_value = perf

        code = MagicMock(metricScore=0.85, metricLatency=7)
        code.evaluate.return_value = (0.85, 7)
        code.getMetricScore.return_value = 0.85
        code.getWeighting.return_value = 0.1
        code.getLatency.return_value = 7
        mock_code_quality.return_value = code

        availability = MagicMock(metricScore=0.65, metricLatency=8)
        availability.score_dataset_and_code_availability.return_value = (0.65, 8)
        availability.getMetricScore.return_value = 0.65
        availability.getWeighting.return_value = 0.2
        availability.getLatency.return_value = 8
        mock_availability.return_value = availability

        card = ScoreCard(url)
        card.setTotalScore(use_multiprocessing=False)

        expected = round(
            0.8 * 0.1
            + 0.6 * 0.1
            + 0.7 * 0.1
            + 0.9 * 0.1
            + 1.0 * 0.2
            + 0.75 * 0.1
            + 0.85 * 0.1
            + 0.65 * 0.2,
            3,
        )
        self.assertAlmostEqual(card.getTotalScore(), expected)
        self.assertGreaterEqual(card.getLatency(), 0)

        buffer = io.StringIO()
        card.printScores()
        out = card.printScores
        with patch("sys.stdout", buffer):
            card.printScores()
        record = json.loads(buffer.getvalue().strip())
        self.assertEqual(record["net_score"], expected)
        self.assertIn("bus_factor", record)
        self.assertIn("size_score", record)


if __name__ == "__main__":
    unittest.main()
