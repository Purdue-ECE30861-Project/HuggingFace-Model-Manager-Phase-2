import hashlib

from src.contracts.artifact_contracts import ArtifactType


def dataset_name_extract_from_url(url: list[str]) -> str:
    if len(url) < 4:
        raise NameError("Invalid HF Url")
    if url[0] != "huggingface.co":
        raise NameError("Invalid HF Url. Must be huggingface.co")
    if url[1] != "datasets":
        raise NameError("Specified type of dataset, hugginface url format requires 'dataset' path")
    print(url)
    return f"{url[3]}"

def model_name_extract_from_url(url: list[str]) -> str:
    if len(url) < 2:
        raise NameError("Invalid HF Url")
    if url[0] != "huggingface.co":
        raise NameError("Invalid HF Url. Must be huggingface.co")
    if len(url) < 3:
        return f"{url[1]}"
    else:
        return f"{url[2]}"

def codebase_name_extract_from_url(url: list[str]) -> str:
    if len(url) < 3:
        raise NameError("Invalid GH Url")
    if url[0] != "github.com":
        raise NameError("Invalid GH Url. Must be github.com")
    return f"{url[1]}/{url[2]}"

def extract_name_from_url(url: str, artifact_type: ArtifactType) -> str:
    if url.startswith("https://"):
        url = url.split("https://")[-1]
    elif url.startswith("http://"):
        url = url.split("http://")[-1]
    url_split = url.split("/")
    match artifact_type:
        case ArtifactType.dataset:
            return dataset_name_extract_from_url(url_split)
        case ArtifactType.code:
            return codebase_name_extract_from_url(url_split)
        case ArtifactType.model:
            return model_name_extract_from_url(url_split)


def generate_unique_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()
