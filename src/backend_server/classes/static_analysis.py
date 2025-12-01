from dataclasses import dataclass
from typing import List, Optional
import re
import logging
import subprocess
import json
import tempfile
import os

logger = logging.getLogger(__name__)


@dataclass
class StaticAnalysisResult:
    has_fixable_issues: bool
    issues_found: List[str]
    fixed_code: Optional[str]
    confidence: float

@dataclass
class LLMAnalysisResult:
    potential_issues: List[str]
    suggested_fix: Optional[str]

@dataclass
class AIDebugResult:
    has_potential_fix: bool
    fixed_code: Optional[str] 
    fix_description: str

class StaticAnalyzer:
    def __init__(self, llm_api):
        self.llm = llm_api
        # load_dotenv()
        self.api_key = os.getenv("GEN_AI_STUDIO_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing GEN_AI_STUDIO_API_KEY environment variable")
    
    
    def comprehensive_static_analysis(self, code: str) -> StaticAnalysisResult:
        """
        combined analysis using syntax checking, pylint, and LLM
        """
        all_issues = []
        
        # Basic syntax checks
        all_issues.extend(self.check_syntax_issues(code))
        all_issues.extend(self.check_import_issues(code))
        
        # Pylint analysis
        pylint_issues = self.run_pylint_analysis(code)
        all_issues.extend(pylint_issues)
        
        if all_issues:
            # Fix detected issues
            fixed_code = self.llm_fix_detected_issues(code, all_issues)
            return StaticAnalysisResult(
                has_fixable_issues=True,
                issues_found=all_issues,
                fixed_code=fixed_code,
                confidence=0.9  # High confidence with pylint
            )
        else:
            # Deep LLM analysis for subtle issues
            llm_analysis = self.llm_analysis(code)
            
            if llm_analysis.potential_issues:
                return StaticAnalysisResult(
                    has_fixable_issues=True,
                    issues_found=llm_analysis.potential_issues,
                    fixed_code=llm_analysis.suggested_fix,
                    confidence=0.6
                )
            else:
                return StaticAnalysisResult(
                    has_fixable_issues=False,
                    issues_found=[],
                    fixed_code=None,
                    confidence=0.95  # Very high confidence
                )

    def check_syntax_issues(self, code: str) -> List[str]:
        """Basic Python syntax checking."""
        issues = []
        
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            # Check if it's actually an indentation issue
            error_msg = str(e).lower()
            if 'indent' in error_msg:
                issues.append(f"Indentation error: {str(e)}")
            else:
                issues.append(f"Syntax error: {str(e)}")
        except IndentationError as e:
            issues.append(f"Indentation error: {str(e)}")
        
        return issues


    def check_import_issues(self, code: str) -> List[str]:
        """
        check for likely import problems
        """

        issues = []
        
        # Check for transformers usage without proper import
        uses_transformers = any(pattern in code for pattern in ['transformers', '.from_pretrained(', 'pipeline(', 'AutoTokenizer', 'AutoModel'])
        
        has_transformers_import = any(pattern in code for pattern in ['from transformers import', 'import transformers'])
        
        if uses_transformers and not has_transformers_import:
            issues.append("Uses transformers functionality but no transformers import found")
        
        if 'torch' in code and 'import torch' not in code:
            issues.append("Uses 'torch' but no torch import found")
                
        return issues
    

    def run_pylint_analysis(self, code: str) -> List[str]:
        """
        run pylint on code and return list of issues found
        """
        issues = []
        try:
            with tempfile.NamedTemporaryFile(mode = 'w', suffix = '.py', delete = False) as f:
                f.write(code)
                temp_file = f.name
            
            result = subprocess.run(
                ['pylint', '--output-format=json', '--disable=C,R', temp_file],
                capture_output=True,
                text=True,
                timeout = 10
            )

            if result.stdout:
                pylint_results = json.loads(result.stdout)
                for issue in pylint_results:
                    if issue['type'] in ('error', 'warning'):
                        issues.append(f"Line {issue['line']}: {issue['message']}")

            os.unlink(temp_file)


        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
        except Exception as e:
            logger.debug(f"pylint analysis failed: {e}")

        return issues
    

    def llm_fix_detected_issues(self, code: str, issues: List[str]) -> str:
        prompt = f"""
        Fix the following specific issues in this Python code. Return ONLY the corrected code.
    
        Issues to fix:
        {chr(10).join(f"- {issue}" for issue in issues)}
    
        Original code:
    ```python
    {code}
    ```

        Fixed code:
        """
        try:
            response = self._make_llm_call(prompt)
            fixed_code = self.extract_code_from_llm_response(response)
            return fixed_code or code
        except Exception as e:
            logger.debug(f"LLM fix failed: {e}")
            return code
    

    def llm_analysis(self, code:str) -> LLMAnalysisResult:
        """LLM analysis for subtle issues that linting may miss"""
        prompt = f"""Analyze this Python code for potential runtime issues. Focus on:
- Missing imports that aren't obvious
- Deprecated methods/APIs
- Variable name issues
- Logic errors

Code:
```python
{code}
```

If you find issues, list them briefly and provide corrected code.
If no issues, respond with "NO_ISSUES_FOUND".

Response format:
ISSUES: [list issues or "none"]
FIXED_CODE: [corrected code or "none"]"""

        try:
            response = self._make_llm_call(prompt)
        
            if "NO_ISSUES_FOUND" in response:
                return LLMAnalysisResult(potential_issues=[], suggested_fix=None)
            
            # Parse LLM response for issues and fixes
            issues = self.parse_llm_issues(response)
            fixed_code = self.extract_code_from_llm_response(response)
            
            return LLMAnalysisResult(
                potential_issues=issues,
                suggested_fix=fixed_code
            )
            
        except Exception as e:
            logger.debug(f"LLM deep analysis failed: {e}")
            return LLMAnalysisResult(potential_issues=[], suggested_fix=None)

    def ai_debug_with_error_context(self, failed_code: str, error_output: str) -> AIDebugResult:
        """Use AI to debug code that failed execution, with full error context"""
        prompt = f"""This Python code failed during execution. Analyze the error and provide a fix.

Failed code:
```python
{failed_code}
```

Runtime error:
{error_output[:500]}

Requirements:
1. Identify the specific cause of the failure
2. Provide corrected code that should work
3. Explain what you fixed in one sentence

Format your response as:
CAUSE: [what caused the error]
FIX: [one sentence explanation]
CODE: [corrected Python code]"""

        try:
            response = self._make_llm_call(prompt)
        
            # Extract fix description
            fix_match = re.search(r'FIX:\s*(.*)', response)
            fix_description = fix_match.group(1) if fix_match else "AI attempted to fix the error"
            
            # Extract fixed code
            fixed_code = self.extract_code_from_llm_response(response)
            
            if fixed_code and fixed_code != failed_code and self.basic_code_validation(fixed_code):
                return AIDebugResult(
                    has_potential_fix=True,
                    fixed_code=fixed_code,
                    fix_description=fix_description
                )
            else:
                return AIDebugResult(
                    has_potential_fix=False,
                    fixed_code=None,
                    fix_description="Could not generate a valid fix"
                )

        except Exception as e:
            logger.debug(f"AI debugging failed: {str(e)}")
            return AIDebugResult(
                has_potential_fix=False,
                fixed_code=None,
                fix_description=f"Debug attempt error: {str(e)}"
            )
    

    def extract_code_from_llm_response(self, response: str) -> Optional[str]:
        """extract python code from LLM response."""
        
        # Try to find code in fenced blocks first
        code_blocks = re.findall(r'```python\n(.*?)\n```', response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()
        
        # Try generic code blocks
        code_blocks = re.findall(r'```\n(.*?)\n```', response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()
        
        # Try to find CODE: section
        code_match = re.search(r'CODE:\s*\n(.*?)(?:\n\n|\Z)', response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        # If no code blocks, try to extract everything after certain triggers
        lines = response.split('\n')
        code_started = False
        code_lines = []
        
        for line in lines:
            if any(trigger in line.lower() for trigger in ['fixed code:', 'corrected code:', 'here is', 'here\'s']):
                code_started = True
                continue
            elif code_started:
                code_lines.append(line)
        
        if code_lines:
            return '\n'.join(code_lines).strip()
        
        return None
    

    def basic_code_validation(self, code: str) -> bool:
        """Basic validation that the code looks reasonable."""
        if not code or len(code.strip()) < 10:
            return False
            
        try:
            # Check if it's valid Python syntax
            compile(code, '<string>', 'exec')
            
            # Check if it has some basic structure
            has_imports = 'import' in code
            has_assignments = '=' in code
            has_function_calls = '(' in code and ')' in code
            
            return has_imports or has_assignments or has_function_calls
            
        except SyntaxError:
            return False
    

    def is_error_potentially_fixable(self, error_message: str) -> bool:
        """quick check if error type is easily fixable"""
        fixable_indicators = [
            "ImportError", "ModuleNotFoundError", "SyntaxError", 
            "NameError", "AttributeError", "IndentationError",
            "unexpected indent", "invalid syntax", "No module named"
        ]
        return any(indicator in error_message for indicator in fixable_indicators)
    

    def parse_llm_issues(self, response: str) -> List[str]:
        """
        parse issues from LLM response
        """
        issues = []

        issues_match = re.search(r'ISSUES:\s*(.*?)(?:\n\w+:|$)', response, re.DOTALL)
        if issues_match:
            issues_text = issues_match.group(1).strip()
            if issues_text.lower() != "none":
                # split by lines and clean up
                for line in issues_text.split('\n'):
                    line = line.strip()
                    if line and not line.lower().startswith('none'):
                        # remove bullet points and clean
                        line = re.sub(r'^[-*•]\s*', '', line)
                        if line:
                            issues.append(line)
        
        return issues
    
        
    def _make_llm_call(self, prompt: str) -> str:
        """Helper method to make standardized LLM calls."""
        try:
            response_text = self.llm.make_prompt(self.api_key, "user", prompt)
            # Parse the JSON response to get just the content
            response_json = json.loads(response_text)
            return response_json['choices'][0]['message']['content']
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Error parsing LLM response: {e}")
            return ""
        except Exception as e:
            logger.debug(f"LLM call failed: {e}")
            return ""