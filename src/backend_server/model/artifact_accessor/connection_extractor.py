from pathlib import Path
import yaml
import os
import re
from bs4 import BeautifulSoup
import requests

from src.backend_server.model.artifact_accessor.name_extraction import extract_name_from_url
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.contracts.artifact_contracts import ArtifactType


def model_identify_attached_datasets(card_info: dict) -> list[str]:
    if "datasets" in card_info:
        return card_info["datasets"]
    return []


GITHUB_URL_RE = re.compile(r"(https?://)?github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
def find_github_urls(root_dir: Path) -> list[str]:
    results = []

    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            full_path = os.path.join(dirpath, fn)

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue

            urls = GITHUB_URL_RE.findall(text)
            if urls:
                cleaned = ["https://github.com/" + u.split("github.com/")[1] if "github.com/" in u else u
                           for u in urls]
                results += cleaned

    return results

def model_identify_attached_codebases(tempdir: Path) -> list[str]:
    github_urls: list[str] = find_github_urls(tempdir)
    github_names: list[str] = []

    for github_url in github_urls:
        github_names.append(extract_name_from_url(github_url, ArtifactType.code))
    return github_names


def model_identify_attached_parent_model_relation(model_name: str) -> str:
    model_url: str = f"https://huggingface.co/{model_name}"
    page = requests.get(model_url)

    soup = BeautifulSoup(page.content, "html.parser")
    this_model_div = soup.find("div", string=lambda s: s and "this model" in s)

    # 2. Ascend until reaching the container that also contains the Quantized row
    container = this_model_div
    while container and not container.find("div", class_="mr-auto"):
        container = container.parent

    if not container:
        raise ValueError("No matching container found")

    # 3. Inside that container, locate the last occurrence of mr-auto *before* this_model_div
    rows = container.find_all("div", class_="mr-auto")

    # The correct one is the last mr-auto before the 'this model' div
    target = None
    for r in rows:
        if r.sourcepos and this_model_div.sourcepos and r.sourcepos < this_model_div.sourcepos:
            target = r

    # Fallback (if sourcepos unavailable in your parser)
    if target is None:
        # linear scan: pick the mr-auto nearest to the this_model_div by DOM order
        for r in reversed(rows):
            if r.find_next(string=lambda s: s and "this model" in s):
                target = r
                break

    value = target.get_text(strip=True)
    return value.lower()

def model_identify_attached_parent_model(model_name: str, card_info: dict) -> tuple[str|None, str|None, str|None]:
    name: str | None = None
    relation: str | None = None
    source: str | None = None

    if "base_model" in card_info:
        name = card_info["base_model"]
        if "base_model_relation" in card_info:
            relation = card_info["base_model_relation"]
            source = "model_card"
        else:
            relation = model_identify_attached_parent_model_relation(model_name)

    return name, relation, source

def model_get_related_artifacts(model_name: str, tempdir: Path, readme: str) -> ModelLinkedArtifactNames:
    model_card_readme: str = readme.split("---")[1]
    card_info: dict = yaml.safe_load(model_card_readme)

    parent_model_name, parent_model_relation, parent_model_source = model_identify_attached_parent_model(model_name, card_info)
    return ModelLinkedArtifactNames(
        linked_dset_names=model_identify_attached_datasets(card_info),
        linked_code_names=model_identify_attached_codebases(tempdir),
        linked_parent_model_name=parent_model_name,
        linked_parent_model_relation=parent_model_relation,
        linked_parent_model_rel_source=parent_model_source,
    )


