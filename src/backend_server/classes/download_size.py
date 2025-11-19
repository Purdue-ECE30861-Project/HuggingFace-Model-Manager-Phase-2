from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.contracts.metric_std import MetricStd
from src.contracts.artifact_contracts import Artifact
from src.backend_server.utils.hf_api import hfAPI
import json
import os
import requests
import logging

logger = logging.getLogger(__name__)


class DownloadSize(MetricStd[float]):
    """
    Metric for analyzing download size and cost of HuggingFace models.
    Provides total download size and breakdown by component.
    """
    metric_name = "Download Size"
    
    def __init__(self, metric_weight=0.1):
        super().__init__(metric_weight)
        self.total_size_bytes = 0
        self.total_size_mb = 0.0
        self.component_sizes = {}
        self.component_breakdown = {}
        self.hf_token = os.getenv('HUGGINGFACE_API_TOKEN')

        # Thresholds (adjust to match expected model size ranges)
        self.size_thresholds = {
            'smallest': 50,      # <= 50 MB: score 1.0
            'small': 500,        # <= 500 MB: score 0.8
            'medium': 2000,      # <= 2 GB: score 0.6
            'large': 10000,      # <= 10 GB: score 0.4
            'largest': 50000     # <= 50 GB: score 0.2
        }

        self.component_categories = {
            'model_weights': ['.bin', '.safetensors', '.h5', '.ckpt', '.pth', '.pt'],
            'config_files': ['.json', '.yaml', '.yml', '.txt'],
            'tokenizer': ['tokenizer.json', 'vocab.txt', 'merges.txt', 'special_tokens_map.json'],
            'documentation': ['README.md', '.md', 'model_card.md'],
            'code': ['.py', '.ipynb', '.sh'],
            'other': []
        }
        
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, *args, **kwargs) -> float:
        """
        Calculate download size score for a model.
        
        Args:
            ingested_path: Path to downloaded artifact files (can be used for local analysis)
            artifact_data: Artifact metadata containing URL
            url (kwarg): Optional explicit URL override
        
        Returns:
            float: Score between 0.0 and 1.0 (higher = smaller/better)
        """
        # Get URL from kwargs, artifact_data, or fail gracefully
        url = kwargs.get('url')
        if not url and hasattr(artifact_data, 'url'):
            url = artifact_data.url
        if not url and hasattr(artifact_data, 'source_url'):
            url = artifact_data.source_url
        
        if not url:
            logger.warning("No URL provided for download size check")
            return 0.0

        try:
            logger.debug(f"Computing download size for {url}")
            api = hfAPI()
            response = json.loads(api.get_info(url, printCLI=False))

            total_size, component_sizes = self._analyze_model_files(url, response)

            if total_size > 0:
                self.total_size_bytes = total_size
                self.total_size_mb = total_size / (1024 * 1024)
                self.component_sizes = component_sizes
                self.component_breakdown = self._calculate_component_breakdown(component_sizes, total_size)
                score = self._calculate_size_score(self.total_size_mb)
                logger.debug(f"Download size analysis complete: {self.total_size_mb:.1f} MB, score: {score}")
                return score
            else:
                logger.warning(f"Could not determine download size for {url}")
                self._reset_metrics()
                return 0.0

        except Exception as e:
            logger.error(f"Error computing download size for {url}: {e}")
            self._reset_metrics()
            return 0.0

    def _reset_metrics(self):
        """Reset all metrics to default values"""
        self.total_size_bytes = 0
        self.total_size_mb = 0.0
        self.component_sizes = {}
        self.component_breakdown = {}

    def _analyze_model_files(self, url: str, response: dict) -> Tuple[int, Dict[str, int]]:
        """Analyze model files to get size information from HF API"""
        try:
            kind = response.get("_requested", {}).get("kind", "model")
            repo_id = response.get("_requested", {}).get("repo_id", "")

            if not repo_id:
                api = hfAPI()
                kind, repo_id = api.parse_hf_url(url)

            return self._get_file_tree_sizes(repo_id, kind)

        except Exception as e:
            logger.debug(f"Error analyzing model files for {url}: {e}")
            return 0, {}

    def _get_file_tree_sizes(self, repo_id: str, kind: str = "model") -> Tuple[int, Dict[str, int]]:
        """Get file sizes from HF API file tree endpoint"""
        try:
            if kind == "model":
                api_url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
            else:
                api_url = f"https://huggingface.co/api/datasets/{repo_id}/tree/main"
            
            headers = {}
            if self.hf_token:
                headers['Authorization'] = f'Bearer {self.hf_token}'

            response = requests.get(api_url, headers=headers, timeout=30)

            if response.status_code == 200:
                files_data = response.json()
                return self._process_file_tree(files_data)
            else:
                logger.debug(f"Failed to fetch file tree from API: {response.status_code}")
                return 0, {}
            
        except Exception as e:
            logger.debug(f"Error getting file tree sizes: {str(e)}")
            return 0, {}
    
    def _process_file_tree(self, files_data: List[dict]) -> Tuple[int, Dict[str, int]]:
        """Process HF API file tree to calculate sizes by component"""
        total_size = 0
        component_sizes = {category: 0 for category in self.component_categories.keys()}

        for file_info in files_data:
            if file_info.get('type') == 'file':
                file_size = file_info.get('size', 0)
                file_path = file_info.get('path', '')

                total_size += file_size

                category = self._categorize_file(file_path)
                component_sizes[category] += file_size

        return total_size, component_sizes
    
    def _categorize_file(self, filename: str) -> str:
        """Categorize file into component category based on path and extension"""
        file_path_lower = filename.lower()
        filename_only = os.path.basename(file_path_lower)

        # First pass: check specific filenames
        for category, patterns in self.component_categories.items():
            for pattern in patterns:
                if not pattern.startswith('.'):
                    if pattern in filename_only:
                        return category
        
        # Second pass: check extensions
        for category, patterns in self.component_categories.items():
            for pattern in patterns:
                if pattern.startswith('.'):
                    if file_path_lower.endswith(pattern):
                        return category
        
        return 'other'
    
    def _calculate_component_breakdown(self, component_sizes: Dict[str, int], total_size: int) -> Dict[str, float]:
        """Calculate size percentages for each component category"""
        if total_size == 0:
            return {category: 0.0 for category in component_sizes.keys()}
        
        return {
            category: (size / total_size) * 100.0
            for category, size in component_sizes.items()
        }
    
    def _calculate_size_score(self, size_mb: float) -> float:
        """Calculate score based on size thresholds"""
        if size_mb <= self.size_thresholds['smallest']:
            return 1.0
        elif size_mb <= self.size_thresholds['small']:
            return 0.8
        elif size_mb <= self.size_thresholds['medium']:
            return 0.6
        elif size_mb <= self.size_thresholds['large']:
            return 0.4
        elif size_mb <= self.size_thresholds['largest']:
            return 0.2
        else:
            return 0.0
        
    # Utility methods for external use
    def get_human_readable_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def get_download_summary(self) -> Dict[str, str]:
        """Get human-readable download summary"""
        if not self.component_sizes:
            return {}
        return {
            category: f"{self.get_human_readable_size(size)} ({self.component_breakdown.get(category, 0):.1f}%)"
            for category, size in self.component_sizes.items()
            if size > 0
        }
    
    def supports_partial_download(self) -> bool:
        """
        Check if model supports meaningful partial downloads.
        Returns True if multiple substantial components exist.
        """
        if not self.component_sizes or self.total_size_bytes == 0:
            return False
        
        # Count non-zero components (excluding 'other')
        non_zero_components = sum(
            1 for category, size in self.component_sizes.items() 
            if size > 0 and category != 'other'
        )
        
        if non_zero_components < 2:
            return False
        
        # Check if components are reasonably distributed
        has_substantial_component = False
        max_percentage = 0
        
        for category, size in self.component_sizes.items():
            if size > 0 and category != 'other':
                percentage = (size / self.total_size_bytes) * 100
                max_percentage = max(max_percentage, percentage)
                
                if percentage > 20.0:
                    has_substantial_component = True

        return has_substantial_component and max_percentage <= 80.0

    # Getter methods for backward compatibility
    def get_total_size_bytes(self) -> int:
        return self.total_size_bytes
    
    def get_total_size_mb(self) -> float:
        return self.total_size_mb
    
    def get_component_sizes(self) -> Dict[str, int]:
        return self.component_sizes
    
    def get_component_breakdown(self) -> Dict[str, float]:
        return self.component_breakdown