# tests/test_metadata.py
import json
import unittest
from unittest.mock import patch, MagicMock
import statistics
# CHANGE THIS IMPORT if your file is named differently:
from src.utils.get_metadata import (
    _repo_id_from_url,
    _normalize_author,
    find_github_links,
    getCollaborators,
    get_collaborators_github,
)

# -----------------------------
# Helpers: _repo_id_from_url, _normalize_author
# -----------------------------

class RepoIdFromUrlTests(unittest.TestCase):
    def test_repo_id_from_url_ok(self):
        self.assertEqual(_repo_id_from_url("https://huggingface.co/google/gemma-2b"), "google/gemma-2b")
        self.assertEqual(_repo_id_from_url("https://huggingface.co/owner/repo/extra/path"), "owner/repo")

    def test_repo_id_from_url_bad(self):
        with self.assertRaises(ValueError):
            _repo_id_from_url("https://huggingface.co/")
        with self.assertRaises(ValueError):
            _repo_id_from_url("https://huggingface.co/onlyowner")


class NormalizeAuthorTests(unittest.TestCase):
    def test_normalize_plain(self):
        self.assertEqual(_normalize_author("Alice"), "Alice")

    def test_normalize_drops_emails_and_html(self):
        self.assertEqual(_normalize_author("Alice <alice@example.com>"), "Alice")
        self.assertEqual(_normalize_author("Bob <bob@x.org>"), "Bob")
        self.assertEqual(_normalize_author("Carol <carol@x.org> <extra@x.org>"), "Carol")
        val = _normalize_author("Dave <d@x.org> <span>junk</span>")
        self.assertEqual(" ".join(val.split()), "Dave junk")   # collapse any extra whitespace

    def test_normalize_filters_bots_and_system(self):
        self.assertIsNone(_normalize_author("dependabot"))
        self.assertIsNone(_normalize_author("github-actions"))
        self.assertIsNone(_normalize_author("foo-bot"))
        self.assertIsNone(_normalize_author("System"))
        self.assertIsNone(_normalize_author(None))
        self.assertIsNone(_normalize_author(""))


# -----------------------------
# Hugging Face: find_github_links
# -----------------------------

class FindGithubLinksTests(unittest.TestCase):
    @patch("backend_server.utils.get_metadata.ModelCard")
    @patch("backend_server.utils.get_metadata.HfApi")
    def test_finds_links_in_cardData_and_readme(self, mHfApi, mModelCard):
        # Mock model_info().cardData with nested github URL
        info = MagicMock()
        info.cardData = {
            "code_repository": "https://github.com/org/repo",
            "nested": {"other": ["x", "https://github.com/another/repo/issues/1"]},
        }
        api = MagicMock()
        api.model_info.return_value = info
        mHfApi.return_value = api

        # Mock ModelCard.load(...).text
        card = MagicMock()
        card.text = """
        # Title
        Some text with https://github.com/foo/bar and also not-a-link.com
        """
        mModelCard.load.return_value = card

        out = find_github_links("https://huggingface.co/org/model")
        self.assertIn("https://github.com/org/repo", out)
        self.assertIn("https://github.com/another/repo/issues/1", out)
        self.assertIn("https://github.com/foo/bar", out)


# -----------------------------
# Hugging Face: getCollaborators
# -----------------------------

class GetCollaboratorsHFTests(unittest.TestCase):
    @patch("backend_server.utils.get_metadata.HfApi")
    def test_get_collaborators_hf_success(self, mHfApi):
        # Create fake commit objects with 'authors' attribute (list of strings)
        class Commit:
            def __init__(self, authors):
                self.authors = authors

        # 4 commits total; first human author picked from authors list
        commits = [
            Commit(["Alice <a@x.org>", "build-bot"]),  # Alice
            Commit(["Alice <a@x.org>"]),               # Alice
            Commit(["Bob <b@x.org>", "bot"]),          # Bob
            Commit(["Alice <a@x.org>", "ci"])          # Alice
        ]  # => Alice:3, Bob:1

        api = MagicMock()
        api.list_repo_commits.return_value = commits
        mHfApi.return_value = api

        avg, std, authors = getCollaborators("https://huggingface.co/org/model", n=4)

        # avg = sum(counts)/n = 4/4 = 1.0
        self.assertAlmostEqual(avg, 1.0, places=6)
        # proportions = [3/4, 1/4] -> sample stdev:
        expected_std = statistics.stdev([3/4, 1/4])
        self.assertAlmostEqual(std, expected_std, places=6)
        self.assertEqual(authors["Alice"], 3)
        self.assertEqual(authors["Bob"], 1)

    @patch("backend_server.utils.get_metadata.HfApi")
    def test_get_collaborators_hf_handles_hub_error(self, mHfApi):
        from huggingface_hub.utils import HfHubHTTPError
        import httpx

        api = MagicMock()
        api.list_repo_commits.side_effect = HfHubHTTPError("no access", response=httpx.Response(400, request=httpx.Request("GET", "https://huggingface.co/org/model")))
        mHfApi.return_value = api

        avg, std, authors = getCollaborators("https://huggingface.co/org/model", n=10)
        self.assertEqual((avg, std, authors), (-1, -1, -1))


# -----------------------------
# GitHub: get_collaborators_github
# -----------------------------

class GetCollaboratorsGithubTests(unittest.TestCase):
    @patch("backend_server.utils.get_metadata.requests.get")
    def test_github_collectors_paginates_and_filters_bots(self, mget):
        # Page 1
        r1 = MagicMock()
        r1.status_code = 200
        r1.json.return_value = [
            {"commit": {"author": {"name": "Alice", "email": "a@x.org"}}},
            {"commit": {"author": {"name": "dependabot", "email": "d@x.org"}}},  # filtered
            {"commit": {"author": {"name": "Bob", "email": "b@x.org"}}},
        ]
        r1.headers = {"Link": '<https://api.github.com/next?page=2>; rel="next"'}
        # Page 2
        r2 = MagicMock()
        r2.status_code = 200
        r2.json.return_value = [
            {"commit": {"author": {"name": "Alice", "email": "a@x.org"}}},
            {"commit": {"author": {"name": "CI-bot", "email": "ci@x.org"}}},  # filtered by regex
        ]
        r2.headers = {"Link": ""}

        mget.side_effect = [r1, r2]

        avg, std, authors = get_collaborators_github("https://github.com/org/repo", n=4)

        # We collected 4 max; effective non-bot commits are Alice(2), Bob(1) => total 3
        # Function uses total=max(1, n)=4 for proportions, average=sum(counts)/4 => 3/4
        self.assertAlmostEqual(avg, 0.75, places=6)
        self.assertIn("Alice <a@x.org>", authors)
        self.assertEqual(authors["Alice <a@x.org>"], 2)
        self.assertEqual(authors["Bob <b@x.org>"], 1)
        # std with proportions [2/4, 1/4] (one author omitted if bot-only)
        self.assertAlmostEqual(std, statistics.stdev([0.5, 0.25]), places=6)

    @patch("backend_server.utils.get_metadata.requests.get")
    def test_github_rate_limit_returns_partial(self, mget):
        # First page ok, second page rate-limited (403 with hint text)
        r1 = MagicMock()
        r1.status_code = 200
        r1.json.return_value = [
            {"commit": {"author": {"name": "Alice", "email": "a@x.org"}}},
        ]
        r1.headers = {"Link": '<https://api.github.com/next?page=2>; rel="next"'}

        r2 = MagicMock()
        r2.status_code = 403
        r2.text = "API rate limit exceeded"
        r2.headers = {"Link": ""}

        mget.side_effect = [r1, r2]

        avg, std, authors = get_collaborators_github("https://github.com/org/repo", n=5)
        # We break and return partial (only first page counted)
        self.assertIn("Alice <a@x.org>", authors)
        # With n=5 total denominator, one commit => avg = 1/5
        self.assertAlmostEqual(avg, 0.2, places=6)


if __name__ == "__main__":
    unittest.main()
