from pathlib import Path
from typing import override

from src.backend_server.model.downloaders.base_downloader import BaseArtifactDownloader
from src.contracts.artifact_contracts import ArtifactType


class KAArtifactDownloader(BaseArtifactDownloader):
    @override
    def download_artifact(self, url: str, artifact_type: ArtifactType, tempdir: Path) -> float:
        with open(tempdir / "README.md", "w") as file:
            file.write(
                """From afar, mount tai looks blackish
                narrow on top and wide at the bottom
                if you flipped it upside down
                it would be narrow at the bottom and wide on top
                'Visiting Mount Tai', by Zhang Zhongchang""")
        return 21 * (1024 ** 3)
