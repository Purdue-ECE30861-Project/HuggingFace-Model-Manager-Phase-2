import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os
import json
import subprocess

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.backend_server.classes.static_analysis import (
    StaticAnalyzer,
    StaticAnalysisResult,
    LLMAnalysisResult,
    AIDebugResult
)


class TestStaticAnalyzerBasics(unittest.TestCase):
    """Test basic StaticAnalyzer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()
        
        # Create mock LLM accessor
        self.mock_llm_accessor = Mock()
        self.mock_api_key = "test-api-key-12345"

    def test_check_syntax_issues_valid_code(self):
        """Test that valid Python code passes syntax check."""
        valid_code = """
def hello():
    print("Hello, World!")
    return 42
"""
        issues = self.analyzer.check_syntax_issues(valid_code)
        self.assertEqual(issues, [])

    def test_check_syntax_issues_syntax_error(self):
        """Test detection of syntax errors."""
        invalid_code = """
def hello()
    print("Missing colon")
"""
        issues = self.analyzer.check_syntax_issues(invalid_code)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("syntax" in issue.lower() for issue in issues))

    def test_check_syntax_issues_indentation_error(self):
        """Test detection of indentation errors."""
        invalid_code = """
def hello():
print("Bad indentation")
"""
        issues = self.analyzer.check_syntax_issues(invalid_code)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("indent" in issue.lower() for issue in issues))

    def test_check_import_issues_transformers_missing(self):
        """Test detection of missing transformers import."""
        code_with_transformers = """
model = AutoModel.from_pretrained("bert-base-uncased")
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
"""
        issues = self.analyzer.check_import_issues(code_with_transformers)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("transformers" in issue.lower() for issue in issues))

    def test_check_import_issues_torch_missing(self):
        """Test detection of missing torch import."""
        code_with_torch = """
tensor = torch.zeros(10)
"""
        issues = self.analyzer.check_import_issues(code_with_torch)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("torch" in issue.lower() for issue in issues))

    def test_check_import_issues_valid_imports(self):
        """Test that code with proper imports passes."""
        code_with_imports = """
import torch
from transformers import AutoModel, AutoTokenizer

model = AutoModel.from_pretrained("bert-base-uncased")
tensor = torch.zeros(10)
"""
        issues = self.analyzer.check_import_issues(code_with_imports)
        self.assertEqual(issues, [])

    def test_basic_code_validation_valid(self):
        """Test validation of valid code."""
        valid_code = """
import os
x = 42
print(x)
"""
        self.assertTrue(self.analyzer.basic_code_validation(valid_code))

    def test_basic_code_validation_too_short(self):
        """Test rejection of very short code."""
        short_code = "x = 1"
        self.assertFalse(self.analyzer.basic_code_validation(short_code))

    def test_basic_code_validation_syntax_error(self):
        """Test rejection of code with syntax errors."""
        invalid_code = """
def broken()
    return 42
"""
        self.assertFalse(self.analyzer.basic_code_validation(invalid_code))

    def test_is_error_potentially_fixable_import_error(self):
        """Test detection of fixable ImportError."""
        self.assertTrue(self.analyzer.is_error_potentially_fixable("ImportError: No module named 'transformers'"))

    def test_is_error_potentially_fixable_syntax_error(self):
        """Test detection of fixable SyntaxError."""
        self.assertTrue(self.analyzer.is_error_potentially_fixable("SyntaxError: invalid syntax"))

    def test_is_error_potentially_fixable_unfixable_error(self):
        """Test detection of unfixable errors."""
        self.assertFalse(self.analyzer.is_error_potentially_fixable("MemoryError: out of memory"))


class TestStaticAnalyzerCodeExtraction(unittest.TestCase):
    """Test code extraction from LLM responses."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()

    def test_extract_code_python_fenced(self):
        """Test extraction from python-fenced code blocks."""
        response = """
Here's the fixed code:
```python
import torch
model = torch.nn.Linear(10, 5)
```

This should work now.
"""
        code = self.analyzer.extract_code_from_llm_response(response)
        self.assertIsNotNone(code)
        self.assertIn("import torch", code)
        self.assertIn("torch.nn.Linear", code)

    def test_extract_code_generic_fenced(self):
        """Test extraction from generic code fences."""
        response = """
```
import torch
model = torch.nn.Linear(10, 5)
```
"""
        code = self.analyzer.extract_code_from_llm_response(response)
        self.assertIsNotNone(code)
        self.assertIn("import torch", code)

    def test_extract_code_with_code_label(self):
        """Test extraction using CODE: label."""
        response = """
CAUSE: Missing import
FIX: Added torch import
CODE:
import torch
model = torch.nn.Linear(10, 5)

This fixes the issue.
"""
        code = self.analyzer.extract_code_from_llm_response(response)
        self.assertIsNotNone(code)
        self.assertIn("import torch", code)

    def test_extract_code_no_code_found(self):
        """Test when no code is found in response."""
        response = "There is no code to extract here."
        code = self.analyzer.extract_code_from_llm_response(response)
        self.assertIsNone(code)


class TestStaticAnalyzerLLMIntegration(unittest.TestCase):
    """Test LLM integration methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()
        self.mock_llm_accessor = Mock()
        self.mock_api_key = "test-api-key"

    def test_make_llm_call_success(self):
        """Test successful LLM call."""
        # Mock successful response
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "This is the LLM response"
                    }
                }
            ]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_response)
        
        result = self.analyzer._make_llm_call("test prompt", self.mock_llm_accessor, self.mock_api_key)
        
        self.assertEqual(result, "This is the LLM response")
        self.mock_llm_accessor.make_prompt.assert_called_once_with(
            self.mock_api_key,
            "user",
            "test prompt"
        )

    def test_make_llm_call_json_error(self):
        """Test LLM call with JSON parsing error."""
        self.mock_llm_accessor.make_prompt.return_value = "invalid json"
        
        result = self.analyzer._make_llm_call("test prompt", self.mock_llm_accessor, self.mock_api_key)
        
        self.assertEqual(result, "")

    def test_make_llm_call_exception(self):
        """Test LLM call with exception."""
        self.mock_llm_accessor.make_prompt.side_effect = Exception("Network error")
        
        result = self.analyzer._make_llm_call("test prompt", self.mock_llm_accessor, self.mock_api_key)
        
        self.assertEqual(result, "")

    def test_parse_llm_issues_with_issues(self):
        """Test parsing of issues from LLM response."""
        response = """
ISSUES:
- Missing import statement
- Variable name typo
- Deprecated function usage
"""
        issues = self.analyzer.parse_llm_issues(response)
        
        self.assertEqual(len(issues), 3)
        self.assertIn("Missing import statement", issues)
        self.assertIn("Variable name typo", issues)
        self.assertIn("Deprecated function usage", issues)

    def test_parse_llm_issues_none(self):
        """Test parsing when no issues found."""
        response = """
ISSUES: none
"""
        issues = self.analyzer.parse_llm_issues(response)
        
        self.assertEqual(len(issues), 0)

    def test_parse_llm_issues_empty(self):
        """Test parsing when ISSUES section not found."""
        response = "Just some text without issues section"
        issues = self.analyzer.parse_llm_issues(response)
        
        self.assertEqual(len(issues), 0)


class TestStaticAnalyzerComprehensiveAnalysis(unittest.TestCase):
    """Test comprehensive static analysis workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()
        self.mock_llm_accessor = Mock()
        self.mock_api_key = "test-api-key"

    @patch('subprocess.run')
    def test_comprehensive_analysis_no_issues(self, mock_subprocess):
        """Test analysis when code has no issues."""
        # Mock pylint returning no issues
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps([])
        )
        
        valid_code = """
import torch

def process_data(x):
    return x * 2
"""
        
        # Mock LLM response saying no issues
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": "NO_ISSUES_FOUND"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.comprehensive_static_analysis(
            valid_code,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, StaticAnalysisResult)
        self.assertFalse(result.has_fixable_issues)
        self.assertEqual(len(result.issues_found), 0)
        self.assertIsNone(result.fixed_code)
        self.assertGreaterEqual(result.confidence, 0.95)

    @patch('subprocess.run')
    def test_comprehensive_analysis_with_syntax_issue(self, mock_subprocess):
        """Test analysis when code has syntax issues."""
        # Mock pylint not being called due to syntax error
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps([])
        )
        
        invalid_code = """
def broken()
    return 42
"""
        
        # Mock LLM fixing the code
        fixed_code = """
def broken():
    return 42
"""
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": f"```python\n{fixed_code}\n```"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.comprehensive_static_analysis(
            invalid_code,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, StaticAnalysisResult)
        self.assertTrue(result.has_fixable_issues)
        self.assertGreater(len(result.issues_found), 0)
        self.assertIsNotNone(result.fixed_code)

    def test_llm_analysis_no_issues(self):
        """Test LLM analysis when no issues found."""
        code = "import torch\nx = 42"
        
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": "NO_ISSUES_FOUND"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.llm_analysis(code, self.mock_llm_accessor, self.mock_api_key)
        
        self.assertIsInstance(result, LLMAnalysisResult)
        self.assertEqual(len(result.potential_issues), 0)
        self.assertIsNone(result.suggested_fix)

    def test_llm_analysis_with_issues(self):
        """Test LLM analysis when issues found."""
        code = "x = torch.zeros(10)"
        
        fixed_code = "import torch\nx = torch.zeros(10)"
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": f"ISSUES:\n- Missing torch import\nFIXED_CODE:\n```python\n{fixed_code}\n```"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.llm_analysis(code, self.mock_llm_accessor, self.mock_api_key)
        
        self.assertIsInstance(result, LLMAnalysisResult)
        self.assertGreater(len(result.potential_issues), 0)
        self.assertIsNotNone(result.suggested_fix)


class TestStaticAnalyzerDebugWithErrorContext(unittest.TestCase):
    """Test AI debugging with error context."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()
        self.mock_llm_accessor = Mock()
        self.mock_api_key = "test-api-key"

    def test_ai_debug_successful_fix(self):
        """Test successful AI debugging."""
        failed_code = "x = torch.zeros(10)"
        error_output = "NameError: name 'torch' is not defined"
        
        fixed_code = "import torch\nx = torch.zeros(10)"
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": f"CAUSE: Missing import\nFIX: Added torch import\nCODE:\n{fixed_code}"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.ai_debug_with_error_context(
            failed_code,
            error_output,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, AIDebugResult)
        self.assertTrue(result.has_potential_fix)
        self.assertIsNotNone(result.fixed_code)
        self.assertIn("import", result.fix_description.lower())

    def test_ai_debug_no_fix_found(self):
        """Test AI debugging when no fix can be found."""
        failed_code = "x = some_undefined_function()"
        error_output = "NameError: name 'some_undefined_function' is not defined"
        
        # LLM returns same code (no fix)
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": f"CAUSE: Function not defined\nFIX: Cannot fix\nCODE:\n{failed_code}"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.ai_debug_with_error_context(
            failed_code,
            error_output,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, AIDebugResult)
        self.assertFalse(result.has_potential_fix)
        self.assertIsNone(result.fixed_code)

    def test_ai_debug_invalid_fixed_code(self):
        """Test AI debugging with syntactically invalid fixed code."""
        failed_code = "x = 42"
        error_output = "Some error"
        
        # LLM returns syntactically invalid code
        invalid_fixed = "def broken(\n    pass"
        mock_llm_response = {
            "choices": [{
                "message": {
                    "content": f"CODE:\n{invalid_fixed}"
                }
            }]
        }
        self.mock_llm_accessor.make_prompt.return_value = json.dumps(mock_llm_response)
        
        result = self.analyzer.ai_debug_with_error_context(
            failed_code,
            error_output,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, AIDebugResult)
        self.assertFalse(result.has_potential_fix)

    def test_ai_debug_exception_handling(self):
        """Test AI debugging handles exceptions gracefully."""
        failed_code = "x = 42"
        error_output = "Some error"
        
        self.mock_llm_accessor.make_prompt.side_effect = Exception("API Error")
        
        result = self.analyzer.ai_debug_with_error_context(
            failed_code,
            error_output,
            self.mock_llm_accessor,
            self.mock_api_key
        )
        
        self.assertIsInstance(result, AIDebugResult)
        self.assertFalse(result.has_potential_fix)
        self.assertEqual(result.fix_description, "Could not generate a valid fix")


class TestStaticAnalyzerPylintIntegration(unittest.TestCase):
    """Test pylint integration (mocked)."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = StaticAnalyzer()

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_run_pylint_analysis_with_errors(self, mock_unlink, mock_tempfile, mock_subprocess):
        """Test pylint analysis detecting errors."""
        # Mock temporary file
        mock_file = Mock()
        mock_file.name = "/tmp/test_file.py"
        mock_tempfile.return_value.__enter__.return_value = mock_file
        
        # Mock pylint output with errors
        pylint_output = [
            {
                "type": "error",
                "line": 5,
                "message": "undefined variable 'x'"
            },
            {
                "type": "warning",
                "line": 10,
                "message": "unused import 'os'"
            }
        ]
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(pylint_output)
        )
        
        code = "some python code"
        issues = self.analyzer.run_pylint_analysis(code)
        
        self.assertEqual(len(issues), 2)
        self.assertTrue(any("undefined variable" in issue for issue in issues))
        self.assertTrue(any("unused import" in issue for issue in issues))

    @patch('subprocess.run')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_run_pylint_analysis_timeout(self, mock_unlink, mock_tempfile, mock_subprocess):
        """Test pylint analysis handles timeout."""
        mock_file = Mock()
        mock_file.name = "/tmp/test_file.py"
        mock_tempfile.return_value.__enter__.return_value = mock_file
        
        mock_subprocess.side_effect = subprocess.TimeoutExpired("pylint", 10)
        
        code = "some python code"
        issues = self.analyzer.run_pylint_analysis(code)
        
        # Should return empty list on timeout
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
