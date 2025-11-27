import subprocess
import tempfile
import json
import time
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, override
from pathlib import Path
from src.contracts.metric_std import MetricStd
from src.contracts.artifact_contracts import Artifact
from src.backend_server.utils.hf_api import hfAPI
from src.backend_server.utils.llm_api import llmAPI
from .static_analysis import StaticAnalysisResult, LLMAnalysisResult, AIDebugResult, StaticAnalyzer
import logging

from ..model.data_store.database_connectors.mother_db_connector import DBManager

logger = logging.getLogger(__name__)

@dataclass
class ReproducibilityResult:
    score: float
    execution_status: str
    error_message: Optional[str]
    fixability_assessment: Optional[str]

class Reproducibility(MetricStd[float]):
    metric_name = "Reproducibility"

    def __init__(self,  metric_weight = 0.1):
        super().__init__(metric_weight)
        self.llm = llmAPI()
        self.static_analyzer = StaticAnalyzer(self.llm)

        self.last_result: Optional[ReproducibilityResult] = None  # ← ADDED THIS LINE

        self.execution_config = {
            "timeout_seconds": 30,
            "memory_limit": "256m",
            "cpu_limit": "0.5",
            "network": "none",
            "max_output_size": 1024 * 10
        }

        self.fixable_errors = {
            "ImportError": 0.8,  # Usually fixable by installing packages
            "ModuleNotFoundError": 0.8,
            "SyntaxError": 0.9,  # Almost always fixable
            "NameError": 0.6,    # Often fixable
            "FileNotFoundError": 0.7,  # Usually path issues
            "AttributeError": 0.4,   # Sometimes fixable
            "TypeError": 0.3,        # Less likely to be fixable
        }

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, database_manager: DBManager, *args, **kwargs) -> float:  # ← NEW METHOD
        """                                                # ← ADDED: docstring
        Calculate reproducibility score for a model.
        
        Args:
            ingested_path: Path to downloaded artifact files (may be used for local execution)
            artifact_data: Artifact metadata containing URL and other info
            url (kwarg): Optional explicit URL override
        
        Returns:
            float: Score between 0.0 and 1.0 indicating reproducibility
        """
        # Get URL from kwargs, artifact_data, or fail gracefully  # ← ADDED: URL extraction logic
        url = kwargs.get('url')                            # ← ADDED
        if not url and hasattr(artifact_data, 'url'):     # ← ADDED
            url = artifact_data.url                        # ← ADDED
        if not url and hasattr(artifact_data, 'source_url'):  # ← ADDED
            url = artifact_data.source_url                 # ← ADDED
        
        if not url:                                        # ← ADDED
            logger.warning("No URL provided for reproducibility check")  # ← ADDED
            return 0.0                                     # ← ADDED

        try:
            logger.debug(f"Computing reproducibility for {url}")
            
            # Step 1: Get model files and identify demo code
            demo_code = self._find_demo_code(url)
            
            if not demo_code:
                logger.debug("No demo code found")
                self.last_result = ReproducibilityResult(
                    score=0.0,
                    execution_status="no_demo_code",
                    error_message="No executable demo code found in model card",
                    fixability_assessment=None
                )
                return 0.0
            
            # Step 2: Attempt safe execution
            result = self._safe_execute_code(demo_code, url)
            self.last_result = result                      # ← ADDED: store result
            
            logger.debug(f"Reproducibility score: {result.score} ({result.execution_status})")
            return result.score                            # ← CHANGED: return instead of setting self.metricScore
            
        except Exception as e:
            logger.warning(f"Error computing reproducibility for {url}: {str(e)}")
            self.last_result = ReproducibilityResult(      # ← ADDED: store error result
                score=0.0,                                 # ← ADDED
                execution_status="exception",              # ← ADDED
                error_message=str(e),                      # ← ADDED
                fixability_assessment=None                 # ← ADDED
            )                                              # ← ADDED
            return 0.0                                     # ← CHANGED: return instead of setting self.metricScore

    def _find_demo_code(self, url: str) -> Optional[str]:
        """
        extracts demo code from model card/README
        """
        try:
            # Get model files using your existing API
            api = hfAPI()
            response = json.loads(api.get_info(url, printCLI=False))
            
            kind = response.get("_requested", {}).get("kind", "model")
            repo_id = response.get("_requested", {}).get("repo_id", "")
            
            if not repo_id:
                kind, repo_id = api.parse_hf_url(url)
            
            readme_content = self._download_model_card(repo_id, kind)

            if readme_content:
                demo_code = self._extract_demo_from_model_card(readme_content)
                if demo_code:
                    logger.debug("Demo code extracted from model card")
                    return demo_code
            
            logger.debug("no demo code found in model card")
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting demo code: {str(e)}")
            return None
        

    def _download_model_card(self, repo_id: str, kind: str = "model") -> Optional[str]:
        """
        Download README.md/model card content from HF repo
        """
        try:
            import requests
            
            if kind == "model":
                readme_url = f"https://huggingface.co/{repo_id}/raw/main/README.md"
            else:
                readme_url = f"https://huggingface.co/datasets/{repo_id}/raw/main/README.md"
            
            response = requests.get(readme_url, timeout=30)
            if response.status_code == 200:
                return response.text
                
            return None
            
        except Exception as e:
            logger.debug(f"Error downloading model card: {str(e)}")
            return None
        
    def _extract_demo_from_model_card(self, readme_content: str) -> Optional[str]:
        """
        extract thte most complete python demo code from the model card.
        """
        demo_sections = self._find_demo_sections(readme_content)

        all_code_blocks = []
        for section in demo_sections:
            python_blocks = re.findall(
                r'```python\n(.*?)\n```',
                section,
                re.DOTALL | re.IGNORECASE
            )
            all_code_blocks.extend(python_blocks)

            if not python_blocks:
                generic_blocks = re.findall(
                    r'```\n(.*?)\n```', 
                    section, 
                    re.DOTALL
                )
                python_like = [block for block in generic_blocks if self._looks_like_python_demo(block)]
                all_code_blocks.extend(python_like)

        if not all_code_blocks:
            all_code_blocks.extend(self._extract_indented_python_code(demo_sections))

        if all_code_blocks:
            return self._select_best_demo_block(all_code_blocks)
        
        return None
    

    def _find_demo_sections(self, readme_content: str) -> List[str]:
        """
        find sections of README/model card that likely contain demo code.
        """
        lines = readme_content.split('\n')
        current_section = []
        demo_sections = []
        in_code_block = False  # Track if we're inside a code fence

        for line in lines:
            # Track code fences to avoid treating # inside code as headers
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                if current_section:
                    current_section.append(line)
                continue
            
            # Only treat as header if NOT in code block
            if not in_code_block and re.match(r'^#+\s+', line):
                if current_section:
                    section_text = '\n'.join(current_section)
                    header = current_section[0].lower()
                    if any(keyword in header for keyword in ['usage', 'how to use', 'quick start', 'example', 'inference', 'getting started']):
                        demo_sections.append(section_text)
                current_section = [line]
            else:
                current_section.append(line)

        if current_section:
            section_text = '\n'.join(current_section)
            header = current_section[0].lower() if current_section else ''
            if any(keyword in header for keyword in ['usage', 'how to use', 'quick start', 'example', 'inference', 'getting started']):
                demo_sections.append(section_text)

        if not demo_sections:
            demo_sections = [readme_content]

        return demo_sections

    

    def _extract_indented_python_code(self, sections: List[str]) -> List[str]:
        code_blocks = []
        
        for section in sections:
            lines = section.split('\n')
            current_block = []
            in_code_block = False
            
            for line in lines:
                stripped = line.strip()
                # Check if line looks like Python code (starts with import, from, etc.)
                if (re.match(r'^(from |import |>>> |def |class |@)', stripped) or
                    re.match(r'^[a-zA-Z_]\w*\s*=', stripped) or  # Any assignment
                    re.search(r'\w+\(.*\)', stripped)):  # Function calls
                    in_code_block = True
                    current_block.append(line)
                elif in_code_block and (line.startswith('    ') or line.startswith('\t') or line.strip() == ''):
                    # Continue code block if indented or empty line
                    current_block.append(line)
                elif in_code_block and current_block:
                    # End of code block
                    code_blocks.append('\n'.join(current_block))
                    current_block = []
                    in_code_block = False
                else:
                    # Reset if we hit non-code content
                    if current_block:
                        code_blocks.append('\n'.join(current_block))
                        current_block = []
                    in_code_block = False
            
            # Add final block if exists
            if current_block:
                code_blocks.append('\n'.join(current_block))
        
        return code_blocks
    

    def _looks_like_python_demo(self, code_block: str) -> bool:
        """
        check if code block looks like python demo code
        """
        # count how many of these patterns appear
        indicators = 0
        
        if 'import' in code_block:
            indicators += 1
        if 'from_pretrained' in code_block:
            indicators += 1
        if re.search(r'(tokenizer|model)\s*=', code_block):
            indicators += 1
        ml_methods = re.findall(r'\.(generate|predict|encode|decode)\(', code_block)
        if len(ml_methods) >= 2:  # has multiple ML method calls
            indicators += 2
        elif len(ml_methods) >= 1:  # has at least one ML method call
            indicators += 1
        if 'pipeline' in code_block:
            indicators += 1
        
        return indicators >= 2 # at least 2 indicators present to have confidence block is python demo code
    

    def _select_best_demo_block(self, code_blocks: List[str]) -> str:
        """
        selects the most complete demo code block, prioritizing blocks with model loading and inference
        """
        best_block = max(code_blocks, key =self._score_demo_block)
        return self._clean_demo_code(best_block)

    def _score_demo_block(self, block: str) -> int:
        score = 0

        # remove interactive prompts
        clean_block = re.sub(r'^>>> ', '', block, flags=re.MULTILINE)
            
        # bonus for model/tokenizer loading
        if re.search(r'\.from_pretrained', clean_block, re.IGNORECASE):
            score += 3
                
        # bonus for actual inference/generation
        if re.search(r'\.(generate|predict|forward)\(', clean_block) or re.search(r'\*\*\w+\)', clean_block):
            score += 2
            
        # bonus for proper imports
        if re.search(r'from transformers import|import torch', clean_block):
            score += 1
                
        # penalty for very short blocks
        if len(clean_block.strip().split('\n')) < 3:
            score -= 2
                
        # bonus for longer, more complete examples
        score += min(len(clean_block.strip().split('\n')) // 3, 3)
            
        return score
    

    def _clean_demo_code(self, raw_code: str) -> str:
        
        lines = raw_code.strip().split('\n')
        cleaned_lines = []

        for line in lines:
            line = re.sub(r'^>>> ', '', line)
            line = re.sub(r'^\.\.\. ?', '', line)  # Added optional space

            line = line.rstrip()

            if not line and not cleaned_lines:
                continue
            
            if line in ('...', '..'):  # Filter out ellipsis remnants
                continue

            cleaned_lines.append(line)

        while cleaned_lines and not cleaned_lines[-1]:
            cleaned_lines.pop()

        return '\n'.join(cleaned_lines)


    def _safe_execute_code(self, demo_code: str, model_url: str) -> ReproducibilityResult:
        """
        1. static analysis with LLM + linting
        2. fix obvious issues if present before running (if changes made cap at 0.5)
        3. single execution attempt in secure sandbox
            4a. AI debugging if 'cleaned' code fails unexpectedly and (score capped at 0.5 if it is not already)
            4b. run again in docker if new problems are identified and supposedly fixed
        5. return final score and execution details
        """
        max_score = 1.0

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 1. static analysis with llm + linting
                logger.debug("performing static analysis")
                analysis_result = self.static_analyzer.comprehensive_static_analysis(demo_code)

                # 2. fix obvious issues if present
                if analysis_result.has_fixable_issues:
                    logger.debug("fixable issues detected, applying preexecution fixes")
                    code_to_run = analysis_result.fixed_code
                    max_score = 0.5 # cap score since fixes were applied
                    issues_fixed = f"pre-execution fixes applied: {', '.join(analysis_result.issues_found)}"
                else:
                    logger.debug("no fixable issues detected in static analysis")
                    code_to_run = demo_code
                    issues_fixed = None

                # 3. execution attempt in secure sandbox
                logger.debug("executing code in docker sandbox")
                result = self._execute_code_in_docker(code_to_run, temp_dir)

                if result.returncode == 0:
                    # sucessful execution, returning appropriate score based on whether fixes were needed
                    score = max_score
                    status = "success" if score == 1.0 else "fixed_and_working"

                    return ReproducibilityResult(
                        score=score,
                        execution_status=status,
                        error_message=issues_fixed,
                        fixability_assessment="Code executed successfully"
                    )
                
                # code failed, attempting AI debugging
                error_output = result.stderr or result.stdout or "unnkown error"
                logger.debug("code failed, attempting AI debugging")

                # 4a. AI debugging, capping score at 0.5 if not already
                max_score = min(max_score, 0.5)
                debug_result = self.static_analyzer.ai_debug_with_error_context(code_to_run, error_output)

                if not debug_result.has_potential_fix:
                    return ReproducibilityResult(
                        score = 0.0,
                        execution_status = "unfixable_error",
                        error_message = error_output[:500],
                        fixability_assessment = "AI debugging could not identify a fix"
                    )
                
                # 4b run again with AI suggested fixes
                logger.debug("Testing AI debugged code")
                debugged_result = self._execute_code_in_docker(debug_result.fixed_code, temp_dir)

                if debugged_result.returncode == 0:
                    return ReproducibilityResult(
                        score = max_score,
                        execution_status = "debugged_and_working", 
                        error_message = f"Original error: {error_output[:200]}",
                        fixability_assessment = f"AI debugging successful: {debug_result.fix_description}"
                    )
                else:
                    debug_error = debugged_result.stderr or debugged_result.stdout
                    return ReproducibilityResult(
                        score = 0.0,
                        execution_status = "debug_failed",
                        error_message = f"Original: {error_output[:200]} | Debug attempt: {debug_error[:200]}",
                        fixability_assessment = "AI debugging attemped failed"
                    )

        except Exception as e:
            return ReproducibilityResult(
                score = 0.0,
                execution_status = "setup_error",
                error_message = str(e),
                fixability_assessment = None
            )
    

    def _execute_code_in_docker(self, code: str, temp_dir: str) -> subprocess.CompletedProcess:
        """Execute code in Docker and return the raw result."""
        # Write code to temporary file
        demo_file = os.path.join(temp_dir, "demo.py")
        with open(demo_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # Build and run Docker command
        docker_cmd = self._build_docker_command(temp_dir)
        
        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.execution_config["timeout_seconds"]
            )
            return result
            
        except subprocess.TimeoutExpired as e:
            # Create a mock result object for timeout
            class TimeoutResult:
                def __init__(self):
                    self.returncode = -1
                    self.stderr = "Execution timed out"
                    self.stdout = ""
            return TimeoutResult()
        
    def _build_docker_command(self, temp_dir: str) -> List[str]:
        """Build Docker command with comprehensive security constraints."""
        return [
            "docker", "run", "--rm", "--read-only",
            "--tmpfs", "/tmp:size=50m,noexec",
            "--network", self.execution_config["network"],
            "--memory", self.execution_config["memory_limit"],
            "--cpus", self.execution_config["cpu_limit"],
            "--memory-swap", self.execution_config["memory_limit"],
            "--user", "nobody", "--workdir", "/workspace",
            "--volume", f"{temp_dir}:/workspace:ro",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--security-opt", "seccomp=default",
            "--pid", "host", "--ipc", "none",
            "--ulimit", "nproc=32", "--ulimit", "nofile=64",
            "python:3.9-slim", "timeout", "30s", "python", "/workspace/demo.py"
        ]
    
    def get_last_result(self) -> Optional[ReproducibilityResult]:  # ← ADDED
        """Get detailed results from last execution"""             # ← ADDED
        return self.last_result