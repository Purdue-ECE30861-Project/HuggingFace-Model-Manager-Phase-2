import unittest
import hashlib
from src.backend_server.model.artifact_accessor.name_extraction import (
    extract_name_from_url,
    generate_unique_id,
    dataset_name_extract_from_url,
    model_name_extract_from_url,
    codebase_name_extract_from_url
)
from src.contracts.artifact_contracts import ArtifactType

class TestNameExtraction(unittest.TestCase):

    def test_dataset_name_extract_valid(self):
        """Test extracting dataset name from split URL list."""
        url_parts = ["huggingface.co", "datasets", "owner", "dataset_name"]
        result = dataset_name_extract_from_url(url_parts)
        self.assertEqual(result, "owner/dataset_name")

    def test_dataset_name_extract_invalid_length(self):
        """Test error when dataset URL is too short."""
        url_parts = ["huggingface.co", "datasets", "owner"]
        with self.assertRaisesRegex(NameError, "Invalid HF Url"):
            dataset_name_extract_from_url(url_parts)

    def test_dataset_name_extract_invalid_domain(self):
        """Test error when domain is not huggingface.co for dataset."""
        url_parts = ["google.com", "datasets", "owner", "dataset_name"]
        with self.assertRaisesRegex(NameError, "Invalid HF Url. Must be huggingface.co"):
            dataset_name_extract_from_url(url_parts)

    def test_dataset_name_extract_invalid_type(self):
        """Test error when 'datasets' path is missing."""
        url_parts = ["huggingface.co", "models", "owner", "dataset_name"]
        with self.assertRaisesRegex(NameError, "Specified type of dataset, hugginface url format requires 'dataset' path"):
            dataset_name_extract_from_url(url_parts)

    def test_model_name_extract_valid(self):
        """Test extracting model name from split URL list."""
        url_parts = ["huggingface.co", "owner", "model_name"]
        result = model_name_extract_from_url(url_parts)
        self.assertEqual(result, "owner/model_name")
    
    def test_model_name_extract_invalid_length(self):
        """Test error when model URL is too short."""
        url_parts = ["huggingface.co", "owner"]
        with self.assertRaisesRegex(NameError, "Invalid HF Url"):
            model_name_extract_from_url(url_parts)

    def test_model_name_extract_invalid_domain(self):
        """Test error when domain is not huggingface.co for model."""
        url_parts = ["google.com", "owner", "model_name"]
        with self.assertRaisesRegex(NameError, "Invalid HF Url. Must be huggingface.co"):
            model_name_extract_from_url(url_parts)

    def test_codebase_name_extract_valid(self):
        """Test extracting codebase name from split URL list."""
        url_parts = ["github.com", "owner", "repo_name"]
        result = codebase_name_extract_from_url(url_parts)
        self.assertEqual(result, "owner/repo_name")

    def test_codebase_name_extract_invalid_length(self):
        """Test error when github URL is too short."""
        url_parts = ["github.com", "owner"]
        with self.assertRaisesRegex(NameError, "Invalid GH Url"):
            codebase_name_extract_from_url(url_parts)

    def test_codebase_name_extract_invalid_domain(self):
        """Test error when domain is not github.com."""
        url_parts = ["gitlab.com", "owner", "repo_name"]
        with self.assertRaisesRegex(NameError, "Invalid GH Url. Must be github.com"):
            codebase_name_extract_from_url(url_parts)
    
    def test_extract_name_from_url_dataset(self):
        """Integration test for dataset URL extraction."""
        url = "https://huggingface.co/datasets/owner/dataset_name"
        result = extract_name_from_url(url, ArtifactType.dataset)
        self.assertEqual(result, "owner/dataset_name")

    def test_extract_name_from_url_model(self):
        """Integration test for model URL extraction."""
        url = "https://huggingface.co/owner/model_name"
        result = extract_name_from_url(url, ArtifactType.model)
        self.assertEqual(result, "owner/model_name")

    def test_extract_name_from_url_code(self):
        """Integration test for codebase URL extraction."""
        url = "https://github.com/owner/repo_name"
        result = extract_name_from_url(url, ArtifactType.code)
        self.assertEqual(result, "owner/repo_name")

    def test_extract_name_from_url_no_protocol(self):
        """Test extraction without http/https prefix."""
        url = "huggingface.co/owner/model_name"
        result = extract_name_from_url(url, ArtifactType.model)
        self.assertEqual(result, "owner/model_name")

    def test_generate_unique_id(self):
        """Test that unique ID generation is consistent and correct format."""
        url = "https://example.com/resource"
        expected = hashlib.md5(url.encode()).hexdigest()
        self.assertEqual(generate_unique_id(url), expected)

if __name__ == '__main__':
    unittest.main()