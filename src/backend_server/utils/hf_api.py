#!/usr/bin/env python3
"""
Fetch and print metadata for a Hugging Face model or dataset from its URL.

Usage:
  python hf_api.py
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse
from functools import lru_cache

import requests

HF_HOSTS = {"huggingface.co", "www.huggingface.co"}

class hfAPI():
    def _strip_empty(self, parts):
        return [p for p in parts if p]


    def parse_hf_url(self, url: str):
        """
        Parse a Hugging Face URL and determine whether it's a model or dataset.
        Returns (kind, repo_id) where kind in {"model","dataset"}.
        Raises ValueError if parsing fails.
        """
        # Accept plain repo ids like "bert-base-uncased" or "username/repo" for convenience
        if not (url.startswith("http://") or url.startswith("https://")):
            # Heuristic: if it contains a slash it's likely "org/repo" -> model by default
            if url.startswith("datasets/"):
                return "dataset", url[len("datasets/") :].strip("/")
            return "model", url.strip("/")

        parsed = urlparse(url)
        if parsed.netloc not in HF_HOSTS:
            raise ValueError(f"Expected a huggingface.co URL, got host '{parsed.netloc}'.")

        path_parts = self._strip_empty(parsed.path.split("/"))
        if not path_parts:
            raise ValueError("URL is missing path segments. Provide a model or dataset URL.")

        # If it's a dataset, the path starts with "datasets/..."
        if path_parts[0].lower() == "datasets":
            kind = "dataset"
            rest = path_parts[1:]
            if not rest:
                raise ValueError("Dataset URL must include a dataset name, e.g. /datasets/squad.")
            # dataset ids can be "owner/name" or just "name"
            # Allow extra segments like 'tree/main' or 'blob/main'. We only keep the first 1–2 segments.
            if rest[0] in {"datasets"}:
                # Handle unusual double "datasets" (rare)
                rest = rest[1:]
            repo_id = rest[0] if (len(rest) == 1 or rest[1] in {"tree", "blob", "resolve"}) else "/".join(rest[:2])
        else:
            # Model URLs are usually /org-or-user/repo
            # Some model URLs may include extra segments like 'tree/main', 'blob/main', etc.
            if len(path_parts) == 1 or path_parts[1] in {"tree", "blob", "resolve"}:
                # One segment (e.g., "bert-base-uncased") or extra path after the first segment
                repo_id = path_parts[0]
            else:
                # Two or more segments -> owner/repo
                repo_id = "/".join(path_parts[:2])
            kind = "model"

        # Sanity check: repo ids should not contain spaces
        repo_id = repo_id.strip("/")
        if not repo_id or re.search(r"\s", repo_id):
            raise ValueError(f"Could not determine a valid repo id from URL '{url}'. Parsed id: '{repo_id}'")
        return kind, repo_id


    def build_api_url(self, kind: str, repo_id: str) -> str:
        if kind == "model":
            return f"https://huggingface.co/api/models/{repo_id}"
        elif kind == "dataset":
            return f"https://huggingface.co/api/datasets/{repo_id}"
        else:
            raise ValueError(f"Unknown kind '{kind}'. Expected 'model' or 'dataset'.")


    def fetch_json(self, api_url: str):
        r = requests.get(api_url, timeout=10)  # no token headers
        r.raise_for_status()
        return r.json()

    @lru_cache(maxsize=128)
    def get_info(self, url, printCLI=True):
        try:
            kind, repo_id = self.parse_hf_url(url)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)

        api_url = self.build_api_url(kind, repo_id)

        try:
            data = self.fetch_json(api_url)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "Unknown"
            detail = e.response.text if e.response is not None else str(e)
            print(f"HTTP error ({status}) while fetching {api_url}:\n{detail}", file=sys.stderr)
            sys.exit(1)
        except requests.RequestException as e:
            print(f"Network error while fetching {api_url}: {e}", file=sys.stderr)
            sys.exit(1)

        if printCLI:
            print(json.dumps(
                {
                    "_requested": {
                        "kind": kind,
                        "repo_id": repo_id,
                        "api_url": api_url,
                        "host": "huggingface.co"
                    },
                    "data": data
                },
                indent=2,
                sort_keys=False
            ))
        else:
            return json.dumps(
                {
                    "_requested": {
                        "kind": kind,
                        "repo_id": repo_id,
                        "api_url": api_url,
                        "host": "huggingface.co"
                    },
                    "data": data
                },
                indent=2,
                sort_keys=False
            )


if __name__ == "__main__":
    apiTester = hfAPI()
    apiTester.get_info("https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct")
