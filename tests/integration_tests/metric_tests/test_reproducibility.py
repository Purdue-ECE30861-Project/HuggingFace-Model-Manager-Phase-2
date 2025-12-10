"""
Unit tests for Reproducibility metric.

Tests the Reproducibility metric which evaluates whether model demo code
can be successfully executed, with or without automated fixes.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.backend_server.classes.reproducibility import Reproducibility, ReproducibilityResult
from src.backend_server.classes.static_analysis import StaticAnalysisResult, AIDebugResult
from src.contracts.artifact_contracts import (
    Artifact,
    ArtifactMetadata,
    ArtifactData,
    ArtifactType
)
from src.backend_server.model.dependencies import DependencyBundle


class TestReproducibilityScoring(unittest.TestCase):
    """Test the scoring logic of Reproducibility metric."""

    def setUp(self):
        """Set up test fixtures."""
        self.metric = Reproducibility(metric_weight=0.1)
        
        # Create test artifact
        self.test_artifact = Artifact(
            metadata=ArtifactMetadata(
                name="test-model",
                id="test-model-123",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://huggingface.co/test/model",
                download_url="https://example.com/download"
            )
        )
        
        # Create mock dependency bundle
        self.mock_dependency_bundle = Mock(spec=DependencyBundle)
        self.mock_llm_accessor = Mock()
        self.mock_dependency_bundle.llm_accessor = self.mock_llm_accessor
        
        self.test_path = Path("/tmp/test_model")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    @patch('src.backend_server.classes.reproducibility.Reproducibility._safe_execute_code')
    def test_score_1_0_clean_code_no_fixes(self, mock_execute, mock_find_demo):
        """Test that clean code with no issues returns 1.0."""
        # Mock finding demo code
        demo_code = "import torch\nprint('Hello')"
        mock_find_demo.return_value = demo_code
        
        # Mock successful execution without any fixes
        mock_execute.return_value = ReproducibilityResult(
            score=1.0,
            execution_status="success",
            error_message=None,
            fixability_assessment="Code executed successfully"
        )
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 1.0, "Clean code should return 1.0")
        self.assertIsNotNone(self.metric.last_result)
        self.assertEqual(self.metric.last_result.execution_status, "success")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    @patch('src.backend_server.classes.reproducibility.Reproducibility._safe_execute_code')
    def test_score_0_5_code_with_fixes(self, mock_execute, mock_find_demo):
        """Test that code requiring fixes returns 0.5."""
        # Mock finding demo code
        demo_code = "print('Missing import')\nx = torch.zeros(10)"
        mock_find_demo.return_value = demo_code
        
        # Mock successful execution after fixes (capped at 0.5)
        mock_execute.return_value = ReproducibilityResult(
            score=0.5,
            execution_status="fixed_and_working",
            error_message="pre-execution fixes applied: Missing import",
            fixability_assessment="Code executed successfully"
        )
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.5, "Fixed code should return 0.5")
        self.assertEqual(self.metric.last_result.execution_status, "fixed_and_working")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    @patch('src.backend_server.classes.reproducibility.Reproducibility._safe_execute_code')
    def test_score_0_5_code_with_debugging(self, mock_execute, mock_find_demo):
        """Test that code requiring AI debugging returns 0.5."""
        # Mock finding demo code
        demo_code = "x = torch.zeros(10)"
        mock_find_demo.return_value = demo_code
        
        # Mock successful execution after AI debugging
        mock_execute.return_value = ReproducibilityResult(
            score=0.5,
            execution_status="debugged_and_working",
            error_message="Original error: NameError",
            fixability_assessment="AI debugging successful: Added import"
        )
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.5, "AI-debugged code should return 0.5")
        self.assertEqual(self.metric.last_result.execution_status, "debugged_and_working")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    @patch('src.backend_server.classes.reproducibility.Reproducibility._safe_execute_code')
    def test_score_0_0_unfixable_code(self, mock_execute, mock_find_demo):
        """Test that unfixable code returns 0.0."""
        # Mock finding demo code
        demo_code = "undefined_function()"
        mock_find_demo.return_value = demo_code
        
        # Mock failed execution that couldn't be fixed
        mock_execute.return_value = ReproducibilityResult(
            score=0.0,
            execution_status="unfixable_error",
            error_message="NameError: name 'undefined_function' is not defined",
            fixability_assessment="AI debugging could not identify a fix"
        )
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0, "Unfixable code should return 0.0")
        self.assertEqual(self.metric.last_result.execution_status, "unfixable_error")

    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    def test_score_0_0_no_demo_code(self, mock_find_demo):
        """Test that missing demo code returns 0.0."""
        # Mock no demo code found
        mock_find_demo.return_value = None
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0, "No demo code should return 0.0")
        self.assertEqual(self.metric.last_result.execution_status, "no_demo_code")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._find_demo_code')
    def test_score_0_0_on_exception(self, mock_find_demo):
        """Test that exceptions return 0.0."""
        # Mock exception during demo code finding
        mock_find_demo.side_effect = Exception("Network error")
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0, "Exceptions should return 0.0")
        self.assertEqual(self.metric.last_result.execution_status, "exception")


class TestReproducibilityDemoCodeExtraction(unittest.TestCase):
    """Test demo code extraction from model cards."""

    def setUp(self):
        """Set up test fixtures."""
        self.metric = Reproducibility(metric_weight=0.1)

    def test_extract_python_fenced_code(self):
        """Test extraction of python-fenced code blocks."""
        readme = """
# Model Usage

Here's how to use this model:
```python
from transformers import AutoModel
model = AutoModel.from_pretrained("model-name")
output = model.generate()
```
"""
        demo_code = self.metric._extract_demo_from_model_card(readme)
        
        self.assertIsNotNone(demo_code)
        self.assertIn("AutoModel", demo_code)
        self.assertIn("from_pretrained", demo_code)

    def test_extract_multiple_code_blocks_selects_best(self):
        """Test that multiple code blocks are evaluated and best is selected."""
        readme = """
# Usage

Short example:
```python
import torch
```

Complete example:
```python
from transformers import AutoModel, AutoTokenizer

model = AutoModel.from_pretrained("bert-base-uncased")
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
output = model.generate()
```
"""
        demo_code = self.metric._extract_demo_from_model_card(readme)
        
        self.assertIsNotNone(demo_code)
        # Should select the longer, more complete example
        self.assertIn("AutoModel", demo_code)
        self.assertIn("AutoTokenizer", demo_code)
        self.assertIn("generate", demo_code)

    def test_no_code_blocks_returns_none(self):
        """Test that README without code returns None."""
        readme = """
# Model Card

This is a great model but there's no code example.
"""
        demo_code = self.metric._extract_demo_from_model_card(readme)
        
        self.assertIsNone(demo_code)

    def test_clean_demo_code_removes_prompts(self):
        """Test that interactive prompts are removed."""
        raw_code = """>>> import torch
>>> model = torch.nn.Linear(10, 5)
>>> output = model(torch.randn(10))
"""
        cleaned = self.metric._clean_demo_code(raw_code)
        
        self.assertNotIn(">>>", cleaned)
        self.assertIn("import torch", cleaned)
        self.assertIn("torch.nn.Linear", cleaned)

    def test_score_demo_block_prefers_complete_examples(self):
        """Test that scoring prefers complete examples."""
        short_block = "import torch"
        
        complete_block = """
from transformers import AutoModel, AutoTokenizer

model = AutoModel.from_pretrained("bert-base-uncased")
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
inputs = tokenizer("Hello", return_tensors="pt")
output = model.generate(**inputs)
"""
        
        short_score = self.metric._score_demo_block(short_block)
        complete_score = self.metric._score_demo_block(complete_block)
        
        self.assertGreater(complete_score, short_score,
                          "Complete examples should score higher")

    def test_looks_like_python_demo_identifies_ml_code(self):
        """Test identification of ML demo code."""
        ml_code = """
from transformers import pipeline
classifier = pipeline("sentiment-analysis")
result = classifier.predict("This is great!")
"""
        self.assertTrue(self.metric._looks_like_python_demo(ml_code))
        
        non_ml_code = "x = 5\ny = 10"
        self.assertFalse(self.metric._looks_like_python_demo(non_ml_code))


class TestReproducibilitySafeExecution(unittest.TestCase):
    """Test safe code execution logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.metric = Reproducibility(metric_weight=0.1)
        self.mock_dependency_bundle = Mock(spec=DependencyBundle)
        self.mock_llm_accessor = Mock()
        self.mock_dependency_bundle.llm_accessor = self.mock_llm_accessor

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._execute_code_in_docker')
    def test_safe_execute_clean_code_returns_1_0(self, mock_docker):
        """Test that clean code with no issues returns score of 1.0."""
        demo_code = "import torch\nprint('Hello')"
        
        # Mock static analysis finding no issues
        with patch.object(self.metric.static_analyzer, 'comprehensive_static_analysis') as mock_analysis:
            mock_analysis.return_value = StaticAnalysisResult(
                has_fixable_issues=False,
                issues_found=[],
                fixed_code=None,
                confidence=0.95
            )
            
            # Mock successful Docker execution
            mock_docker.return_value = Mock(returncode=0, stdout="Hello", stderr="")
            
            # Execute
            result = self.metric._safe_execute_code(
                demo_code,
                "https://huggingface.co/model",
                self.mock_dependency_bundle
            )
            
            # Verify score is 1.0 (not capped)
            self.assertEqual(result.score, 1.0,
                           "Clean code should return 1.0, not 0.5")
            self.assertEqual(result.execution_status, "success")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._execute_code_in_docker')
    def test_safe_execute_fixed_code_returns_0_5(self, mock_docker):
        """Test that fixed code returns score of 0.5 (capped)."""
        demo_code = "x = torch.zeros(10)"  # Missing import
        fixed_code = "import torch\nx = torch.zeros(10)"
        
        # Mock static analysis finding and fixing issues
        with patch.object(self.metric.static_analyzer, 'comprehensive_static_analysis') as mock_analysis:
            mock_analysis.return_value = StaticAnalysisResult(
                has_fixable_issues=True,
                issues_found=["Missing torch import"],
                fixed_code=fixed_code,
                confidence=0.9
            )
            
            # Mock successful Docker execution
            mock_docker.return_value = Mock(returncode=0, stdout="", stderr="")
            
            # Execute
            result = self.metric._safe_execute_code(
                demo_code,
                "https://huggingface.co/model",
                self.mock_dependency_bundle
            )
            
            # Verify score is capped at 0.5
            self.assertEqual(result.score, 0.5,
                           "Fixed code should be capped at 0.5")
            self.assertEqual(result.execution_status, "fixed_and_working")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._execute_code_in_docker')
    def test_safe_execute_failed_then_debugged_returns_0_5(self, mock_docker):
        """Test that code that fails then gets AI-debugged returns 0.5."""
        demo_code = "import torch\nx = torch.zeros(10)"
        
        # Mock static analysis finding no issues initially
        with patch.object(self.metric.static_analyzer, 'comprehensive_static_analysis') as mock_analysis:
            mock_analysis.return_value = StaticAnalysisResult(
                has_fixable_issues=False,
                issues_found=[],
                fixed_code=None,
                confidence=0.95
            )
            
            # Mock first execution failing, second succeeding
            mock_docker.side_effect = [
                Mock(returncode=1, stdout="", stderr="RuntimeError: CUDA not available"),
                Mock(returncode=0, stdout="", stderr="")  # After debugging
            ]
            
            # Mock AI debugging
            with patch.object(self.metric.static_analyzer, 'ai_debug_with_error_context') as mock_debug:
                debugged_code = "import torch\nx = torch.zeros(10, device='cpu')"
                mock_debug.return_value = AIDebugResult(
                    has_potential_fix=True,
                    fixed_code=debugged_code,
                    fix_description="Changed to CPU device"
                )
                
                # Execute
                result = self.metric._safe_execute_code(
                    demo_code,
                    "https://huggingface.co/model",
                    self.mock_dependency_bundle
                )
                
                # Verify score is capped at 0.5 (due to debugging)
                self.assertLessEqual(result.score, 0.5,
                                   "AI-debugged code should be capped at 0.5")
                self.assertEqual(result.execution_status, "debugged_and_working")

    @patch.dict(os.environ, {'GEN_AI_STUDIO_API_KEY': 'test-key-123'})
    @patch('src.backend_server.classes.reproducibility.Reproducibility._execute_code_in_docker')
    def test_safe_execute_unfixable_returns_0_0(self, mock_docker):
        """Test that unfixable code returns 0.0."""
        demo_code = "undefined_function()"
        
        # Mock static analysis finding no syntactic issues
        with patch.object(self.metric.static_analyzer, 'comprehensive_static_analysis') as mock_analysis:
            mock_analysis.return_value = StaticAnalysisResult(
                has_fixable_issues=False,
                issues_found=[],
                fixed_code=None,
                confidence=0.95
            )
            
            # Mock execution failing
            mock_docker.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="NameError: name 'undefined_function' is not defined"
            )
            
            # Mock AI debugging unable to fix
            with patch.object(self.metric.static_analyzer, 'ai_debug_with_error_context') as mock_debug:
                mock_debug.return_value = AIDebugResult(
                    has_potential_fix=False,
                    fixed_code=None,
                    fix_description="Could not identify fix"
                )
                
                # Execute
                result = self.metric._safe_execute_code(
                    demo_code,
                    "https://huggingface.co/model",
                    self.mock_dependency_bundle
                )
                
                # Verify score is 0.0
                self.assertEqual(result.score, 0.0,
                               "Unfixable code should return 0.0")
                self.assertEqual(result.execution_status, "unfixable_error")


class TestReproducibilityMetricProperties(unittest.TestCase):
    """Test metric properties and configuration."""

    def test_metric_name(self):
        """Test that metric has correct name."""
        metric = Reproducibility(metric_weight=0.1)
        self.assertEqual(metric.metric_name, "Reproducibility")

    def test_metric_weight(self):
        """Test that metric weight is properly set."""
        metric = Reproducibility(metric_weight=0.15)
        self.assertEqual(metric.get_weight(), 0.15)

    def test_get_last_result_initially_none(self):
        """Test that last_result is None initially."""
        metric = Reproducibility(metric_weight=0.1)
        self.assertIsNone(metric.get_last_result())

    def test_execution_config_defaults(self):
        """Test that execution config has proper defaults."""
        metric = Reproducibility(metric_weight=0.1)
        
        self.assertEqual(metric.execution_config["timeout_seconds"], 30)
        self.assertEqual(metric.execution_config["memory_limit"], "256m")
        self.assertEqual(metric.execution_config["network"], "none")

    def test_fixable_errors_configuration(self):
        """Test that fixable errors are properly configured."""
        metric = Reproducibility(metric_weight=0.1)
        
        self.assertIn("ImportError", metric.fixable_errors)
        self.assertIn("SyntaxError", metric.fixable_errors)
        self.assertGreater(metric.fixable_errors["ImportError"], 0.5)


class TestReproducibilityDockerCommand(unittest.TestCase):
    """Test Docker command generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.metric = Reproducibility(metric_weight=0.1)

    def test_build_docker_command_structure(self):
        """Test that Docker command has proper security settings."""
        temp_dir = "/tmp/test_dir"
        cmd = self.metric._build_docker_command(temp_dir)
        
        # Verify it's a list
        self.assertIsInstance(cmd, list)
        
        # Verify key security settings
        self.assertIn("docker", cmd)
        self.assertIn("--rm", cmd)
        self.assertIn("--read-only", cmd)
        self.assertIn("--network", cmd)
        self.assertIn("none", cmd)
        self.assertIn("--user", cmd)
        self.assertIn("nobody", cmd)
        
        # Verify image and command
        self.assertIn("python:3.9-slim", cmd)
        self.assertIn("python", cmd)

    def test_build_docker_command_contains_volume_mount(self):
        """Test that Docker command mounts temp directory."""
        temp_dir = "/tmp/test_dir"
        cmd = self.metric._build_docker_command(temp_dir)
        
        # Find volume mount argument
        volume_args = [arg for arg in cmd if temp_dir in arg]
        self.assertGreater(len(volume_args), 0,
                          "Should contain volume mount with temp directory")


class TestReproducibilityURLHandling(unittest.TestCase):
    """Test URL extraction from artifact data."""

    def setUp(self):
        """Set up test fixtures."""
        self.metric = Reproducibility(metric_weight=0.1)
        self.mock_dependency_bundle = Mock(spec=DependencyBundle)

    def test_uses_artifact_data_url(self):
        """Test that URL is correctly extracted from artifact.data.url."""
        artifact = Artifact(
            metadata=ArtifactMetadata(
                name="test-model",
                id="test-123",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://huggingface.co/bert-base-uncased",
                download_url="https://example.com/download"
            )
        )
        
        with patch.object(self.metric, '_find_demo_code') as mock_find:
            mock_find.return_value = None
            
            self.metric.calculate_metric_score(
                Path("/tmp"),
                artifact,
                self.mock_dependency_bundle
            )
            
            # Verify _find_demo_code was called with correct URL
            mock_find.assert_called_once_with("https://huggingface.co/bert-base-uncased")

    def test_uses_kwarg_url_if_provided(self):
        """Test that explicit URL kwarg overrides artifact URL."""
        artifact = Artifact(
            metadata=ArtifactMetadata(
                name="test-model",
                id="test-123",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://huggingface.co/default-model",
                download_url="https://example.com/download"
            )
        )
        
        with patch.object(self.metric, '_find_demo_code') as mock_find:
            mock_find.return_value = None
            
            self.metric.calculate_metric_score(
                Path("/tmp"),
                artifact,
                self.mock_dependency_bundle,
                url="https://huggingface.co/override-model"
            )
            
            # Verify _find_demo_code was called with override URL
            mock_find.assert_called_once_with("https://huggingface.co/override-model")


if __name__ == "__main__":
    unittest.main()
