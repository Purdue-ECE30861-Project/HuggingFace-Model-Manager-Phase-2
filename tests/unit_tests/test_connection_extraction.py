import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.backend_server.model.artifact_accessor.connection_extraction import (
    model_identify_attached_datasets,
    find_github_urls,
    model_identify_attached_codebases,
    model_identify_attached_parent_model_relation,
    model_identify_attached_parent_model,
    model_get_related_artifacts
)
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames

class TestConnectionExtraction(unittest.TestCase):

    def test_model_identify_attached_datasets(self):
        """Test dataset identification from card info dictionary."""
        card_info = {"datasets": ["dataset1", "dataset2"]}
        self.assertEqual(model_identify_attached_datasets(card_info), ["dataset1", "dataset2"])
        
        card_info_empty = {}
        self.assertEqual(model_identify_attached_datasets(card_info_empty), [])

    def test_find_github_urls(self):
        """Test searching for github URLs in files within a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Create dummy file with github urls
            file1 = path / "readme.md"
            file1.write_text("Check out https://github.com/user/repo and github.com/user2/repo2")
            
            # Create dummy file without urls
            file2 = path / "other.txt"
            file2.write_text("Just some text")
            
            urls = find_github_urls(path)
            
            expected_urls = ["https://github.com/user/repo", "github.com/user2/repo2"]
            self.assertEqual(len(urls), 2)
            for url in expected_urls:
                self.assertIn(url, urls)

    @patch("src.backend_server.model.artifact_accessor.connection_extraction.find_github_urls")
    @patch("src.backend_server.model.artifact_accessor.connection_extraction.extract_name_from_url")
    def test_model_identify_attached_codebases(self, mock_extract, mock_find):
        """Test identification of attached codebases using mocks."""
        mock_find.return_value = ["https://github.com/user/repo"]
        mock_extract.return_value = "user/repo"
        
        names = model_identify_attached_codebases(Path("/tmp"))
        
        self.assertEqual(names, ["user/repo"])
        mock_find.assert_called_once()
        mock_extract.assert_called_once()

    @patch("src.backend_server.model.artifact_accessor.connection_extraction.requests.get")
    def test_model_identify_attached_parent_model_relation(self, mock_get):
        """Test parsing of parent model relation from HTML content."""
        mock_response = MagicMock()
        # Simulate HTML where 'mr-auto' div precedes 'this model' div in a common container
        html_content = """
        <div>
            <div class="mr-auto">Quantized</div>
            <div>
                <div>this model</div>
            </div>
        </div>
        """
        mock_response.content = html_content.encode('utf-8')
        mock_get.return_value = mock_response

        relation = model_identify_attached_parent_model_relation("some-model")
        self.assertEqual(relation, "quantized")

    def test_model_identify_attached_parent_model_from_card(self):
        """Test identifying parent model when info is in the model card."""
        card_info = {
            "base_model": "base-model-name",
            "base_model_relation": "finetune"
        }
        name, relation, source = model_identify_attached_parent_model("current-model", card_info)
        
        self.assertEqual(name, "base-model-name")
        self.assertEqual(relation, "finetune")
        self.assertEqual(source, "model_card")

    @patch("src.backend_server.model.artifact_accessor.connection_extraction.model_identify_attached_parent_model_relation")
    def test_model_identify_attached_parent_model_from_webpage(self, mock_relation):
        """Test identifying parent model when info requires webpage scraping."""
        mock_relation.return_value = "quantized"
        card_info = {
            "base_model": "base-model-name"
            # Missing base_model_relation
        }
        
        name, relation, source = model_identify_attached_parent_model("current-model", card_info)
        
        self.assertEqual(name, "base-model-name")
        self.assertEqual(relation, "quantized")
        self.assertEqual(source, "model_webpage")

    @patch("src.backend_server.model.artifact_accessor.connection_extraction.model_identify_attached_parent_model")
    @patch("src.backend_server.model.artifact_accessor.connection_extraction.model_identify_attached_codebases")
    @patch("src.backend_server.model.artifact_accessor.connection_extraction.model_identify_attached_datasets")
    def test_model_get_related_artifacts(self, mock_dsets, mock_code, mock_parent):
        """Test aggregating all related artifacts."""
        # Setup mocks
        mock_dsets.return_value = ["dataset1"]
        mock_code.return_value = ["user/repo"]
        mock_parent.return_value = ("parent-model", "relation", "source")
        
        readme_content = """---
datasets: [dataset1]
base_model: parent-model
---
Some description
"""
        result = model_get_related_artifacts("model-name", Path("."), readme_content)
        
        self.assertIsInstance(result, ModelLinkedArtifactNames)
        self.assertEqual(result.linked_dset_names, ["dataset1"])
        self.assertEqual(result.linked_code_names, ["user/repo"])
        self.assertEqual(result.linked_parent_model_name, "parent-model")
        self.assertEqual(result.linked_parent_model_relation, "relation")
        self.assertEqual(result.linked_parent_model_rel_source, "source")

if __name__ == '__main__':
    unittest.main()