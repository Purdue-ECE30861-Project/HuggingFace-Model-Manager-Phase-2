import hashlib
from pathlib import Path
import yaml

from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.contracts.artifact_contracts import ArtifactType


def model_identify_attached_datasets(card_info: dict) -> list[str]:
    if "datasets" in card_info:
        return card_info["datasets"]
    return []

def model_identify_attached_codebases(readme: str) -> list[str]:
    pass

def model_identify_attached_parent_model(card_info: dict) -> tuple[str, str, str]:
    raise NotImplementedError()

def model_get_related_artifacts(tempdir: Path, readme: str, config_json: dict) -> ModelLinkedArtifactNames:
    # MICHAEL RAY (MALINKYZUBR) AKA DUMBSHIT FORGOT TO IMPLEMENT> IMPLEMENT ASAP OR DIE! -Michael Ray

    model_card_readme: str = readme.split("---")[1]
    card_info: dict = yaml.safe_load(model_card_readme)

    parent_model_name, parent_model_relation, parent_model_source = model_identify_attached_parent_model(card_info)
    return ModelLinkedArtifactNames(
        linked_dset_names=model_identify_attached_datasets(card_info),
        linked_code_names=model_identify_attached_codebases(readme),
        linked_parent_model_name=parent_model_name,
        linked_parent_model_relation=parent_model_relation,
        linked_parent_model_rel_source=parent_model_source,
    )


def extract_name_from_url(url: str, artifact_type: ArtifactType) -> str:
    raise NotImplementedError()


def generate_unique_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()
