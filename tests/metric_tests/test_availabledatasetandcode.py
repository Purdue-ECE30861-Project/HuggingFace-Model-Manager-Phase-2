import unittest
from unittest.mock import patch
from src.backend_server.classes.available_datasets_and_code import AvailableDatasetAndCode


class TestAvailableDatasetAndCode(unittest.TestCase):
    @patch("src.backend_server.classes.available_datasets_and_code.find_github_links", return_value={"https://github.com/org/repo"})
    def test_code_found_dataset_missing(self, _):
        m = AvailableDatasetAndCode()
        ds = m.score_dataset_availability(url="https://hf.co/model/x", datasetURL=None)
        cs = m.score_code_availability(url="https://hf.co/model/x", githubURL=None)
        total = 0.5 * ds + 0.5 * cs
        self.assertTrue(0.0 <= ds <= 1.0)
        self.assertTrue(0.0 <= cs <= 1.0)
        self.assertTrue(0.0 <= total <= 1.0)

    def test_both_provided(self):
        m = AvailableDatasetAndCode()
        ds = m.score_dataset_availability(url=None, datasetURL="https://datasets.org/dataX")
        cs = m.score_code_availability(url=None, githubURL="https://github.com/org/repo")
        total = 0.5 * ds + 0.5 * cs
        self.assertTrue(0.0 <= ds <= 1.0)
        self.assertTrue(0.0 <= cs <= 1.0)
        self.assertTrue(0.0 <= total <= 1.0)

if __name__ == "__main__":
    unittest.main()