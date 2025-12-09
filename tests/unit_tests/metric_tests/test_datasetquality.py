import unittest
from unittest.mock import patch
import json

from src.backend_server.classes.dataset_quality import DatasetQuality

# A tiny fake HF API client that returns JSON strings like hfAPI.get_info()
class FakeHFAPI:
    def __init__(self, payloads_by_url):
        self.payloads = payloads_by_url  # {url: dict_for_data_key}

    def get_info(self, url: str, printCLI: bool = False) -> str:
        data = self.payloads.get(url, {})
        return json.dumps({"data": data})


class TestDatasetQuality(unittest.TestCase):
    def test_no_links_returns_zero(self):
        # If there are no dataset links and none provided, function returns (0.0, 0)
        with patch("backend_server.classes.DatasetQuality.find_dataset_links", return_value=[]):
            dq = DatasetQuality()
            score, ms = dq.computeDatasetQuality(
                url="https://huggingface.co/org/model", datasetURL=None
            )
            self.assertEqual(score, 0.0)
            self.assertEqual(ms, 0)

    def test_single_provided_dataset_url(self):
        # When datasetURL is provided, find_dataset_links is NOT used; hfAPI must be patched
        payloads = {
            "https://datasets.org/ds1": {
                "likes": 100,
                "downloads": 5000,
                "license": "MIT",
                "cardData": {"task_categories": ["text-classification"]},
            }
        }
        with patch("backend_server.classes.DatasetQuality.hfAPI") as HF:
            HF.return_value = FakeHFAPI(payloads)
            dq = DatasetQuality()
            score, ms = dq.computeDatasetQuality(
                url="ignored", datasetURL="https://datasets.org/ds1"
            )
            self.assertTrue(0.0 <= score <= 1.0)
            self.assertGreaterEqual(ms, 0)

    def test_inferred_multiple_datasets_average(self):
        links = [
            "https://huggingface.co/datasets/a",
            "https://huggingface.co/datasets/b",
        ]
        # Patch link discovery to return two datasets
        with patch("backend_server.classes.DatasetQuality.find_dataset_links", return_value=links):
            # Make one very weak and one strong dataset to ensure averaging works
            payloads = {
                links[0]: {
                    "likes": 0,
                    "downloads": 0,
                    "license": None,
                    "cardData": {"task_categories": []},
                },
                links[1]: {
                    "likes": 3000,
                    "downloads": 200_000,
                    "license": "apache-2.0",
                    "cardData": {"task_categories": ["a", "b", "c", "d", "e"]},
                },
            }
            with patch("backend_server.classes.DatasetQuality.hfAPI") as HF:
                HF.return_value = FakeHFAPI(payloads)
                dq = DatasetQuality()
                score, ms = dq.computeDatasetQuality(
                    url="https://huggingface.co/org/model", datasetURL=None
                )
                # Should be between the poor and strong dataset scores
                self.assertGreater(score, 0.1)
                self.assertLessEqual(score, 1.0)
                self.assertGreaterEqual(ms, 0)


if __name__ == "__main__":
    unittest.main()