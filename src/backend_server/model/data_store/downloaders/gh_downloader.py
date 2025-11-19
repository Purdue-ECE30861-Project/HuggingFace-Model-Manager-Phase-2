import os
from pathlib import Path
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError

from src.contracts.artifact_contracts import ArtifactType


class GHArtifactDownloader:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _validate_url(self, url: str) -> bool:
        """Internal method to validate URL format"""
        return url.startswith(('http://github.com', 'https://github.com'))

    def _get_repo_id_from_url(self, url: str, artifact_type: ArtifactType) -> str:
        """Extract owner/repo from GitHub URL"""
        split: list[str] = url.split("/")
        
        # Remove empty strings and filter out protocol/host
        parts = [part for part in split if part and part not in ['http:', 'https:', 'github.com']]
        
        # Remove .git suffix if present
        if parts and parts[-1].endswith('.git'):
            parts[-1] = parts[-1][:-4]
        
        if len(parts) < 2:
            raise NameError("Invalid GitHub URL: must contain owner and repository")
        
        owner = parts[0]
        repo = parts[1]
        
        match artifact_type:
            case ArtifactType.code:
                return f"{owner}/{repo}"
            case ArtifactType.model:
                raise TypeError("Cannot retrieve model from GitHub URL, specify HuggingFace URL")
            case ArtifactType.dataset:
                raise TypeError("Cannot retrieve dataset from GitHub URL, specify HuggingFace URL")

    def _github_clone(self, repo_id: str, tempdir: Path, artifact_type: ArtifactType):
        """Clone GitHub repository to tempdir"""
        try:
            # Construct GitHub URL
            github_url = f"https://github.com/{repo_id}.git"
            
            # Clone the repository using GitPython
            # depth=1 for shallow clone to save time and space
            Repo.clone_from(
                github_url,
                str(tempdir),
                depth=1
            )
        except GitCommandError as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "does not exist" in error_msg or "repository not found" in error_msg:
                raise FileNotFoundError("Requested repository doesn't exist")
            else:
                raise FileNotFoundError(f"Failed to clone repository: {e}")
        except Exception as e:
            raise FileNotFoundError(f"Failed to clone repository: {e}")

    def download_artifact(self, url: str, artifact_type: ArtifactType, tempdir: Path) -> int:
        """Download GitHub repository and return the size of the downloaded artifact"""
        size: int = 0

        repo_id: str = self._get_repo_id_from_url(url, artifact_type)

        self._github_clone(repo_id, tempdir, artifact_type)

        # Calculate total size of downloaded repository
        for root, dirs, files in os.walk(tempdir):
            # Skip .git directory to match actual content size
            dirs[:] = [d for d in dirs if d != '.git']
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size += os.path.getsize(file_path)
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    pass

        return size
