import hashlib
from huggingface_hub import model_info, dataset_info
from src.contracts.artifact_contracts import ArtifactType


def dataset_name_extract_from_url(url: list[str]) -> str:
    if len(url) < 4:
        raise NameError("Invalid HF Url")
    if url[0] != "huggingface.co":
        print(url)
        if url[0] != "www.kaggle.com":
            raise NameError("Invalid HF Url. Must be huggingface.co")
    if url[1] != "datasets":
        raise NameError("Specified type of dataset, hugginface url format requires 'dataset' path")
    name = f"{url[2]}-{url[3]}"
    if url[0] == "huggingface.co":
        name = url[3]
        try:
            dataset_info(name)
        except:
            name = f"{url[2]}-{url[3]}"
    return name

def model_name_extract_from_url(url: list[str]) -> str:
    print(url)
    if len(url) < 2:
        raise NameError("Invalid HF Url")
    if url[0] != "huggingface.co":
        raise NameError("Invalid HF Url. Must be huggingface.co")
    if len(url) < 3:
        return f"{url[1]}"
    else:
        name = url[2]
        try:
            model_info(name)
        except:
            name = f"{url[1]}-{url[2]}"
        return name

def codebase_name_extract_from_url(url: list[str]) -> str:
    if len(url) < 3:
        raise NameError("Invalid GH Url")
    if url[0] != "github.com":
        raise NameError("Invalid GH Url. Must be github.com")
    name = f"{url[1]}-{url[2]}"
    if name.endswith(".git"):
        name = name[:-4]
    return name

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
