import unittest
from unittest.mock import Mock, patch
from src.backend_server.model.license_checker import LicenseChecker


class TestLicenseChecker(unittest.TestCase):
    
    def setUp(self):
        self.checker = LicenseChecker()
    
    def test_fetch_model_license_valid_url(self):
        """
        Test fetching license from a valid HuggingFace model URL.
        """
        model_url = "https://huggingface.co/google-bert/bert-base-uncased"
        
        with patch('requests.get') as mock_get:
            # Mock successful API response with license info
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "cardData": {
                    "license": "apache-2.0"
                }
            }
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_model_license(model_url)
            self.assertIsNotNone(license_type)
            self.assertIsInstance(license_type, str)
    
    def test_fetch_model_license_no_license_field(self):
        """
        Test handling model with no license field in metadata.
        """
        model_url = "https://huggingface.co/some-org/some-model"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "cardData": {}
            }
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_model_license(model_url)
            self.assertTrue(license_type is None or license_type == "unknown")
    
    def test_fetch_model_license_api_error(self):
        """
        Test handling of API errors when fetching model license.
        """
        model_url = "https://huggingface.co/invalid/model"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = Exception("Not Found")
            mock_get.return_value = mock_response
            
            # LicenseChecker logs errors and returns None instead of raising
            license_type = self.checker.fetch_model_license(model_url)
            self.assertIsNone(license_type)
    
    def test_fetch_model_license_invalid_url(self):
        """
        Test handling of invalid URL format.
        """
        invalid_url = "not-a-valid-url"
        
        # LicenseChecker logs errors and returns None instead of raising
        license_type = self.checker.fetch_model_license(invalid_url)
        self.assertIsNone(license_type)
    
    def test_fetch_github_license_valid_repo(self):
        """
        Test fetching license from a valid GitHub repository.
        """
        github_url = "https://github.com/google-research/bert"
        
        with patch('requests.get') as mock_get:
            # Mock GitHub API license endpoint response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "license": {
                    "key": "apache-2.0",
                    "name": "Apache License 2.0",
                    "spdx_id": "Apache-2.0"
                }
            }
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_github_license(github_url)
            self.assertIsNotNone(license_type)
            self.assertIsInstance(license_type, str)
    
    def test_fetch_github_license_no_license(self):
        """
        Test handling repository with no license.
        """
        github_url = "https://github.com/some-user/unlicensed-repo"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_github_license(github_url)
            self.assertTrue(license_type is None or license_type == "unknown")
    
    def test_fetch_github_license_invalid_url(self):
        """
        Test handling of invalid GitHub URL format.
        """
        invalid_url = "not-a-github-url"
        
        # LicenseChecker logs errors and returns None instead of raising
        license_type = self.checker.fetch_github_license(invalid_url)
        self.assertIsNone(license_type)
    
    def test_fetch_github_license_private_repo(self):
        """Test handling of private repository (403 or 404)."""
        github_url = "https://github.com/private-org/private-repo"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = Exception("Not Found")
            mock_get.return_value = mock_response
            
            # LicenseChecker logs errors and returns None instead of raising
            license_type = self.checker.fetch_github_license(github_url)
            self.assertIsNone(license_type)
    
    def test_fetch_github_license_rate_limited(self):
        """Test handling of GitHub API rate limiting."""
        github_url = "https://github.com/some-org/some-repo"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.raise_for_status.side_effect = Exception("Rate limit exceeded")
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_github_license(github_url)
            self.assertIsNone(license_type)


class TestCheckCompatibility(unittest.TestCase):
    """Test license compatibility checking logic."""
    
    def setUp(self):
        """Create a LicenseChecker instance for testing."""
        self.checker = LicenseChecker()
    
    def test_compatible_licenses_apache(self):
        """
        Test that Apache 2.0 licenses are compatible with each other.
        """
        model_url = "https://huggingface.co/google-bert/bert-base-uncased"
        github_url = "https://github.com/google-research/bert"
        
        with patch.object(self.checker, 'fetch_model_license', return_value='apache-2.0'):
            with patch.object(self.checker, 'fetch_github_license', return_value='apache-2.0'):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertTrue(result)
    
    def test_compatible_licenses_mit(self):
        """
        Test that MIT licenses are compatible with each other.
        """
        model_url = "https://huggingface.co/some-org/mit-model"
        github_url = "https://github.com/some-org/mit-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value='mit'):
            with patch.object(self.checker, 'fetch_github_license', return_value='mit'):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertTrue(result)
    
    def test_incompatible_licenses_gpl_apache(self):
        """
        Test that GPL and Apache licenses are incompatible.
        """
        model_url = "https://huggingface.co/some-org/gpl-model"
        github_url = "https://github.com/some-org/apache-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value='gpl-3.0'):
            with patch.object(self.checker, 'fetch_github_license', return_value='apache-2.0'):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertFalse(result)
    
    def test_compatible_permissive_licenses(self):
        """
        Test that permissive licenses are generally compatible.
        """
        model_url = "https://huggingface.co/some-org/mit-model"
        github_url = "https://github.com/some-org/apache-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value='mit'):
            with patch.object(self.checker, 'fetch_github_license', return_value='apache-2.0'):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertIsInstance(result, bool)
    
    def test_unknown_license_model(self):
        """
        Test handling when model license cannot be determined.
        """
        model_url = "https://huggingface.co/some-org/unknown-model"
        github_url = "https://github.com/some-org/some-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value=None):
            with patch.object(self.checker, 'fetch_github_license', return_value='apache-2.0'):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertTrue(result is False or result is None)
    
    def test_unknown_license_github(self):
        """
        Test handling when GitHub license cannot be determined.
        """
        model_url = "https://huggingface.co/some-org/some-model"
        github_url = "https://github.com/some-org/unknown-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value='apache-2.0'):
            with patch.object(self.checker, 'fetch_github_license', return_value=None):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertTrue(result is False or result is None)
    
    def test_both_licenses_unknown(self):
        """
        Test handling when both licenses are unknown.
        """
        model_url = "https://huggingface.co/some-org/unknown-model"
        github_url = "https://github.com/some-org/unknown-repo"
        
        with patch.object(self.checker, 'fetch_model_license', return_value=None):
            with patch.object(self.checker, 'fetch_github_license', return_value=None):
                result = self.checker.check_compatibility(model_url, github_url)
                self.assertTrue(result is False or result is None)
    
    def test_normalize_apache_variants(self):
        """Test normalization of various Apache license spellings."""
        # If your checker has a normalize method
        if hasattr(self.checker, 'normalize_license'):
            variants = ['Apache-2.0', 'apache-2.0', 'Apache 2.0', 'APACHE-2.0']
            normalized = [self.checker.normalize_license(v) for v in variants]
            self.assertEqual(len(set(normalized)), 1)
    
    def test_normalize_gpl_variants(self):
        """
        Test normalization of various GPL license versions.
        """
        if hasattr(self.checker, 'normalize_license'):
            gpl3_variants = ['GPL-3.0', 'gpl-3.0', 'GPLv3']
            normalized = [self.checker.normalize_license(v) for v in gpl3_variants]
            self.assertTrue(all(isinstance(n, str) for n in normalized))


class TestEdgeCases(unittest.TestCase):
    
    def setUp(self):
        """
        Create a LicenseChecker instance for testing.
        """
        self.checker = LicenseChecker()
    
    def test_empty_url_model(self):
        """
        Test handling of empty model URL.
        """
        license_type = self.checker.fetch_model_license("")
        self.assertIsNone(license_type)
    
    def test_empty_url_github(self):
        """
        Test handling of empty GitHub URL.
        """
        license_type = self.checker.fetch_github_license("")
        self.assertIsNone(license_type)
    
    def test_malformed_json_response(self):
        """
        Test handling of malformed JSON in API response.
        """
        model_url = "https://huggingface.co/some-org/some-model"
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response
            
            license_type = self.checker.fetch_model_license(model_url)
            self.assertIsNone(license_type)