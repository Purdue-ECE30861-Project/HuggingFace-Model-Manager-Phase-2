import unittest
import tempfile
import shutil
from pathlib import Path
from src.contracts.metric_std import MetricStd
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactType, ArtifactData
from src.contracts.model_rating import ModelRating
CLASS_DIR = "src.backend_server.classes"
MODULE_PREFIX = "src.backend_server.classes"

CANDIDATE_METHODS = [
    "calculate_metric_score",
    "score",
    "evaluate",
    "run",
    "set_params",
    "set_params_and_score",  # conservative
]

def _make_fake_artifact(tmpdir: str):
    # Provide a flexible fake artifact object with common fields metrics may expect
    metadata = ArtifactMetadata(name="fake-model", type=ArtifactType("model"), id="fake-id")
    data = ArtifactData(url=f"file://{tmpdir}", download_url=f"file://{tmpdir}")
    return Artifact(metadata=metadata, data=data)

class TestModelRaterCalculations(unittest.TestCase):
    def setUp(self):
        # create temporary directory with a few files to emulate an ingested artifact repo
        self.tmpdir = Path(tempfile.mkdtemp(prefix="hfmm_test_"))
        Path(self.tmpdir, "README.md").write_text("# dummy repo")
        Path(self.tmpdir, "main.py").write_text("print('hello')")
        Path(self.tmpdir, "data.csv").write_text("a,b,c\n1,2,3")
        self.artifact = _make_fake_artifact(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_metric_classes_produce_values_without_errors(self):
        rating: ModelRating = ModelRating.generate_rating(self.tmpdir, self.artifact, processes=2)
        self.assertNotEqual(rating, None)
        pass

if __name__ == "__main__":
    unittest.main()