# test_hf_api.py
import json
import sys
import unittest
from unittest.mock import patch

import requests

from src.utils.hf_api import hfAPI

hf_api = hfAPI()


class ParseHfUrlTests(unittest.TestCase):
    def test_parse_model_urls(self):
        cases = {
            # plain repo ids
            "bert-base-uncased": ("model", "bert-base-uncased"),
            "someuser/somerepo": ("model", "someuser/somerepo"),
            # http(s) URLs, 1-part and 2-part
            "https://huggingface.co/bert-base-uncased": ("model", "bert-base-uncased"),
            "https://huggingface.co/someuser/somerepo": ("model", "someuser/somerepo"),
            # extra path segments should be ignored for the repo id
            "https://huggingface.co/bert-base-uncased/tree/main": ("model", "bert-base-uncased"),
            "https://huggingface.co/someuser/somerepo/tree/main": ("model", "someuser/somerepo"),
            "https://huggingface.co/someuser/somerepo/blob/main/file": ("model", "someuser/somerepo"),
            "https://huggingface.co/someuser/somerepo/resolve/main/model.safetensors": ("model", "someuser/somerepo"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(hf_api.parse_hf_url(url), expected)

    def test_parse_dataset_urls_are_parsed(self):
        # Your parser supports datasets even if build_api_url doesn't.
        cases = {
            "datasets/squad": ("dataset", "squad"),
            "https://huggingface.co/datasets/squad": ("dataset", "squad"),
            "https://huggingface.co/datasets/user/name": ("dataset", "user/name"),
            "https://huggingface.co/datasets/name/tree/main": ("dataset", "name"),
            "https://huggingface.co/datasets/user/name/tree/main": ("dataset", "user/name"),
            "https://huggingface.co/datasets/datasets/squad": ("dataset", "squad"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(hf_api.parse_hf_url(url), expected)

    def test_parse_invalid_host_raises(self):
        with self.assertRaises(ValueError):
            hf_api.parse_hf_url("https://example.com/bert-base-uncased")

    def test_parse_missing_path_raises(self):
        with self.assertRaises(ValueError):
            hf_api.parse_hf_url("https://huggingface.co/")

    def test_parse_whitespace_repo_raises(self):
        with self.assertRaises(ValueError):
            hf_api.parse_hf_url("https://huggingface.co/user/my repo")


class BuildApiUrlTests(unittest.TestCase):
    def test_build_api_url_model(self):
        self.assertEqual(
            hf_api.build_api_url("model", "bert-base-uncased"),
            "https://huggingface.co/api/models/bert-base-uncased",
        )

    def test_build_api_url_bad_kind_raises(self):
        with self.assertRaises(ValueError):
            hf_api.build_api_url("weird", "x")


class FetchJsonTests(unittest.TestCase):
    class _Resp:
        def __init__(self, status_code=200, payload=None, text="", url=""):
            self.status_code = status_code
            self._payload = payload if payload is not None else {}
            self.text = text
            self.url = url

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                err = requests.HTTPError(f"{self.status_code} error for {self.url}")
                err.response = self
                raise err

    @patch("requests.get")
    def test_fetch_json_ok(self, mget):
        resp = self._Resp(200, {"ok": True}, url="https://huggingface.co/api/models/bert-base-uncased")
        mget.return_value = resp
        out = hf_api.fetch_json("https://huggingface.co/api/models/bert-base-uncased")
        self.assertEqual(out, {"ok": True})
        # called without token/headers in your current implementation
        args, kwargs = mget.call_args
        self.assertEqual(args[0], "https://huggingface.co/api/models/bert-base-uncased")
        self.assertIn("timeout", kwargs)
        self.assertNotIn("headers", kwargs)

    @patch("requests.get")
    def test_fetch_json_raises_http_error(self, mget):
        bad = self._Resp(status_code=500, text="boom", url="https://huggingface.co/api/models/x")
        mget.return_value = bad
        with self.assertRaises(requests.HTTPError):
            hf_api.fetch_json("https://huggingface.co/api/models/x")


class GetInfoTests(unittest.TestCase):
    @patch("builtins.print")
    @patch("requests.get")
    def test_get_info_prints_json_when_printCLI_true(self, mget, mprint):
        class _R(FetchJsonTests._Resp):
            pass

        mget.return_value = _R(200, {"hello": "world"}, url="https://huggingface.co/api/models/bert-base-uncased")
        hf_api.get_info("https://huggingface.co/bert-base-uncased", printCLI=True)

        # Ensure exactly one JSON blob printed
        self.assertTrue(mprint.called)
        printed = "".join(str(args[0]) for args, _ in mprint.call_args_list)
        blob = json.loads(printed)
        self.assertIn("_requested", blob)
        self.assertEqual(blob["data"], {"hello": "world"})
        self.assertEqual(blob["_requested"]["kind"], "model")
        self.assertEqual(blob["_requested"]["repo_id"], "bert-base-uncased")

    @patch("requests.get")
    def test_get_info_returns_json_string_when_printCLI_false(self, mget):
        class _R(FetchJsonTests._Resp):
            pass

        mget.return_value = _R(200, {"ok": True}, url="https://huggingface.co/api/models/someuser/somerepo")
        out = hf_api.get_info("https://huggingface.co/someuser/somerepo", printCLI=False)
        blob = json.loads(out)
        self.assertEqual(blob["_requested"]["repo_id"], "someuser/somerepo")
        self.assertEqual(blob["data"], {"ok": True})

    def test_get_info_bad_url_exits_2(self):
        # parse_hf_url raises -> get_info sys.exit(2)
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as ctx:
                hf_api.get_info("https://example.com/not-hf", printCLI=False)
        self.assertEqual(ctx.exception.code, 2)

    @patch("requests.get")
    def test_get_info_http_error_exits_1(self, mget):
        # fetch_json raises HTTPError -> get_info sys.exit(1)
        class _R(FetchJsonTests._Resp):
            pass
        mget.return_value = _R(500, text="boom", url="https://huggingface.co/api/models/x")

        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as ctx:
                hf_api.get_info("https://huggingface.co/x", printCLI=False)
        self.assertEqual(ctx.exception.code, 1)

    @patch("requests.get", side_effect=requests.RequestException("no internet"))
    def test_get_info_network_error_exits_1(self, _mget):
        with patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as ctx:
                hf_api.get_info("https://huggingface.co/x", printCLI=False)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()