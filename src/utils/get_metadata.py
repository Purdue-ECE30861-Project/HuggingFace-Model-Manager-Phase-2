# Count unique contributors from Hugging Face without cloning
# pip install huggingface_hub
from __future__ import annotations
import os, re
from urllib.parse import urlparse
from collections import Counter
from typing import Optional
from huggingface_hub import HfApi, ModelCard
from huggingface_hub.utils import HfHubHTTPError
import statistics
from dotenv import load_dotenv, dotenv_values
import requests
import base64

BOT_RE = re.compile(r"(bot|ci|action|autobot|dependabot|github-actions)", re.I)

def _repo_id_from_url(url: str) -> str:
    p = urlparse(url)
    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) < 2:
        raise ValueError("Invalid HF URL; expected https://huggingface.co/<owner>/<repo>")
    return f"{parts[0]}/{parts[1]}"

def _normalize_author(label: str | None) -> str | None:
    if not label:
        return None
    label = re.sub(r"<[^>]+>", "", label).strip()  # drop emails
    if not label or label.lower() == "system" or BOT_RE.search(label):
        return None
    return label

def getCollaborators(hf_url: str, n: int = 100, branch: str | None = None) -> int:
    """Return # of unique human authors among the last n commits."""
    repo_id = _repo_id_from_url(hf_url)

    # Use token if available (needed for gated/private repos), else anonymous.
    load_dotenv()
    tok = os.getenv("HF_TOKEN")
    api = HfApi(token=tok or False)

    try:
        commits = api.list_repo_commits(repo_id, revision=branch)[:n]
    except HfHubHTTPError as e:
        # Common causes: repo is gated/private and you didn't supply HF_TOKEN,
        # or you haven't accepted the license.
       print(f"Unable to list commits for {repo_id}: {e}")
       return -1, -1, -1

    authors = {}
    for c in commits:
        # Prefer the first human author string if present
        author = None
        if getattr(c, "authors", None):
            for a in c.authors:
                a = _normalize_author(a)
                if a:
                    author = a
                    break
        if author and author in authors:
            authors[author] += 1
        elif author and author not in authors:
            authors[author] = 1

    # get proportion of commits for each author
    average = 0
    proportions = []
    for writers in authors:
        proportions.append(authors[writers] / n)
        average += authors[writers]
    
    std = statistics.stdev(proportions)
    average = average / n

    return average, std, authors

# Regex to capture GitHub repo links
GITHUB_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)

def get_model_metadata(url: str):
    """
    Retrieve parameter count, file sizes, and model type for a Hugging Face model.
    Returns (param_count, file_sizes, model_type).
    """
    api = HfApi()
    model_id = url.split("huggingface.co/")[-1]

    info = api.model_info(model_id)

    param_count = None
    if hasattr(info, "cardData") and info.cardData:
        param_count = info.cardData.get("parameters")

    file_sizes = []
    if hasattr(info, "siblings"):
        for f in info.siblings:
            if hasattr(f, "size") and f.size:
                file_sizes.append(f.size)

    model_type = "general"
    if hasattr(info, "pipeline_tag") and info.pipeline_tag:
        model_type = info.pipeline_tag

    return param_count, file_sizes, model_type

def find_github_links(url):
    api = HfApi()
    model_id = _repo_id_from_url(url)

    # 1. Get model info (includes cardData)
    info = api.model_info(model_id)
    links = set()

    # From cardData if present
    if getattr(info, "cardData", None):
        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    yield from walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from walk(v)
            elif isinstance(obj, str):
                if "github.com" in obj:
                    yield obj
        links.update(walk(info.cardData))

    # 2. Get README text and scan for links
    card = ModelCard.load(model_id)
    readme = card.text if hasattr(card, "text") else card.content
    links.update(GITHUB_URL_RE.findall(readme))

    return list(links)

# Regex for HF dataset links
DATASET_URL_RE = re.compile(r"https?://huggingface\.co/datasets/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+")

def find_dataset_links(url: str):
    api = HfApi()
    model_id = _repo_id_from_url(url)
    try:
        info = api.model_info(model_id)
    except requests.exceptions.HTTPError:
        return []
    links = set()

    # 1. From cardData if present
    if getattr(info, "cardData", None):
        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    yield from walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from walk(v)
            elif isinstance(obj, str):
                if "huggingface.co/datasets" in obj:
                    yield obj
        links.update(walk(info.cardData))

    # 2. From top-level API metadata (HF sometimes provides this directly)
    if hasattr(info, "datasets") and info.datasets:
        for ds in info.datasets:
            if isinstance(ds, str):
                links.add(f"https://huggingface.co/datasets/{ds}")

    # 3. From README text (ModelCard)
    card = ModelCard.load(model_id)
    readme = getattr(card, "text", getattr(card, "content", ""))
    links.update(DATASET_URL_RE.findall(readme))

    return list(links)

def get_github_readme(url: str) -> str:
    """
    Fetch README.md content from a GitHub repo using the GitHub REST API.
    Expects format: https://github.com/<owner>/<repo>
    Returns decoded README text, or "" if not found.
    """
    try:
        links = find_github_links(url)
        if links:
            github_url = links[0]
            m = re.match(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", github_url.strip())
            if not m:
                raise ValueError(f"Bad GitHub URL: {github_url}")
            owner, repo = m.group(1), m.group(2)

            url = f"https://api.github.com/repos/{owner}/{repo}/readme"
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "readme-fetcher/1.0"}
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                content = r.json().get("content", "")
                return base64.b64decode(content).decode("utf-8")
            else:
                return ""
        else:
            return ""
    except Exception as e:
        return ""


# --- Last-N commit authors from a GitHub repo (no token) ---
_BOT_RE = re.compile(r"(?:\[(?:bot)\]|bot$|^dependabot|^github-actions)", re.I)

def get_collaborators_github(github_url: str, n: int = 100, branch: str | None = None):
    m = re.match(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", github_url.strip())
    if not m: raise ValueError(f"Bad GitHub URL: {github_url}")
    owner, repo = m.group(1), m.group(2)

    per_page = max(1, min(100, n))
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={per_page}" + (f"&sha={branch}" if branch else "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "commit-sampler-noauth/1.0"}
    commits = []

    # paginate until we collect n or hit rate limit
    while url and len(commits) < n:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            break  # return partial results if rate-limited
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list): break
        commits.extend(data)
        # parse Link header for next
        link = r.headers.get("Link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip()[1:-1]  # strip <>
                break
        url = nxt
    commits = commits[:n]

    authors = {}
    for c in commits:
        a = (c.get("commit") or {}).get("author") or {}
        name, email = (a.get("name") or "").strip(), (a.get("email") or "").strip()
        if not name and not email:
            gh = c.get("author") or {}
            name, email = (gh.get("login") or gh.get("name") or "").strip(), ""
        if _BOT_RE.search(name): 
            continue
        key = f"{name} <{email}>" if name and email else (name or email)
        if not key: 
            continue
        authors[key] = authors.get(key, 0) + 1

    total = max(1, n)
    proportions = [cnt / total for cnt in authors.values()]
    average = sum(authors.values()) / total
    std = statistics.stdev(proportions) if len(proportions) > 1 else 0.0
    return average, std, authors

if __name__ == "__main__":
    # # test access token
    hfurl = "https://huggingface.co/google-bert/bert-base-uncased"
    # avg, std, authors = getCollaborators(url, n=100)
    # if avg == -1 or std == -1 or authors == -1:
    #     print("Unable to access Repo")
    # else:
    #     print("Unique collaborators (last 100):", len(authors))
    #     print("Average percentage of commits by individuals: ", avg)
    #     print("Standard deviation of commit percentage by individuals: ", std)

    github_url = "https://github.com/huggingface/transformers"
    avg, std, authors = get_collaborators_github(github_url, n=100)
    print("Unique collaborators (last 100):", len(authors))
    print("Average percentage of commits by individuals: ", avg)
    print("Standard deviation of commit percentage by individuals: ", std)

    print(find_github_links(hfurl))
    

    # bf = BusFactor()
    # bf.setNumContributors(github_url)
    # print("Num contributors: ", bf.getNumContributors())
    # print("Metric Score: ", bf.getMetricScore())
