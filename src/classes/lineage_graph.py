#!/usr/bin/env python3
import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from huggingface_hub import HfApi, hf_hub_download, ModelCard
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

@dataclass
class ModelNode:
    """
    Represents a model in the lineage graph.
    """
    model_id: str
    model_name: str
    parents: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class LineageGraph:
    """
    Constructs and manages model lineage graphs by analyzing HuggingFace metadata.
    
    The graph identifies parent models through:
    1. config.json fields like base_model, parent_model, base_model_name_or_path
    2. Model card mentions of fine-tuned or derived models
    3. Model tags and metadata
    """
    
    def __init__(self):
        token = os.getenv("HF_TOKEN")
        self.api = HfApi(token=token if token else None)
        self.nodes: Dict[str, ModelNode] = {}
        self.processing: Set[str] = set()
        
    def extract_repo_id_from_url(self, url: str) -> str:
        """
        Extract repo_id from a HuggingFace URL.
        """
        p = urlparse(url)
        parts = [seg for seg in p.path.split("/") if seg]
        return parts[-1]
    
    def fetch_model_metadata(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Fetch config.json, model card, and model info for a given HuggingFace model.
        
        Returns:
            Tuple of (config_dict, card_text, model_info)
        """
        try:
            model_id = self.extract_repo_id_from_url(url)
            
            # Fetch config.json
            config = None
            try:
                config_path = hf_hub_download(
                    repo_id=model_id,
                    filename="config.json",
                    repo_type="model"
                )
                with open(config_path, 'r') as f:
                    config = json.load(f)
            except Exception as e:
                logger.debug(f"Could not fetch config.json for {model_id}: {e}")
            
            # Fetch model card text
            card_text = None
            try:
                readme_path = hf_hub_download(
                        repo_id=model_id,
                        filename="README.md",
                        repo_type="model"
                    )
                with open(readme_path, 'r', encoding='utf-8') as f:
                    card_text = f.read()
                        
            except Exception as e:
                p = urlparse(url)
                parts = [seg for seg in p.path.split("/") if seg]
                model_id = f"{parts[0]}/{parts[1]}"
                logger.warning(f"Could not fetch model card for {model_id}: {e}. Trying alternative repo_id.")
                readme_path = hf_hub_download(
                        repo_id=model_id,
                        filename="README.md",
                        repo_type="model"
                    )
                with open(readme_path, 'r', encoding='utf-8') as f:
                    card_text = f.read()
                    
            return config, card_text
            
        except Exception as e:
            logger.warning(f"Error fetching metadata for {url}: {e}")
            return None, None#, None
    
    def extract_parent_from_config(self, config: Dict | None) -> Optional[str]:
        """
        Extract parent model ID from config.json metadata.
        """
        if not config:
            return None
        
        parent_fields = [
            "base_model",
            "base_model_name_or_path", 
            "parent_model",
            "_name_or_path",
            "model_name_or_path"
        ]
        
        for field in parent_fields:
            if field in config:
                parent = config[field]
                if isinstance(parent, str):
                    return parent
                if isinstance(parent, list):
                    return parent[0]
        return None
    
    def extract_parents_from_card(self, card_text: str | None, model_id: str) -> List[str]:
        """
        Extract parent model references from model card text.
        
        Looks for patterns like:
        - "fine-tuned from [model]"
        - "based on [model]"
        - "derived from [model]"
        - "distilled from [model]"
        """
        if not card_text:
            return []
        
        parents = []
        
        # Markdown links with context - [text](url)
        link_pattern = r"\[([^\]]+)\]\(https://huggingface\.co/([a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_.-]+)?)/?\)"
        for match in re.finditer(link_pattern, card_text):
            link_text = match.group(1).lower()
            parent_id = match.group(2)
            
            # Check if this link is in a parent-indicating context
            start_pos = max(0, match.start() - 100)
            context = card_text[start_pos:match.start()].lower()
            
            parent_indicators = [
                'fine-tuned', 'fine tuned', 'finetuned',
                'based on', 'based off',
                'derived from', 'derived',
                'distilled from', 'distilled version',
                'trained on', 'built on',
                'version of', 'variant of',
                'uses', 'using'
            ]
            
            # If context or link text suggests this is a parent model
            is_parent_link = any(indicator in context for indicator in parent_indicators)
            
            if (is_parent_link) and parent_id != model_id:
                parents.append(parent_id)
        
        # Direct HuggingFace URLs (backup)
        url_pattern = r"https://huggingface\.co/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)"
        for match in re.finditer(url_pattern, card_text):
            parent_id = match.group(1)
            # Exclude self and common non-model pages
            if parent_id != model_id and not any(x in parent_id for x in ['datasets', 'spaces', 'docs', 'models']):
                parents.append(parent_id)
        
        return list(set(parents))
    
    
    def build_lineage(self, url: str, depth: int = 2) -> ModelNode:
        """
        Build lineage graph for a model by recursively analyzing parents.
        
        Args:
            url: HuggingFace model URL
            depth: How many levels up to trace (0 = just this model)
        
        Returns:
            ModelNode representing the queried model with parent relationships
        """
        model_id = self.extract_repo_id_from_url(url)
        
        # Check if we've already processed this model
        if model_id in self.nodes:
            return self.nodes[model_id]
        
        # Prevent infinite recursion
        if model_id in self.processing:
            logger.warning(f"Circular dependency detected for {model_id}")
            return self.nodes.get(model_id, ModelNode(model_id=model_id, model_name=model_id.split("/")[-1]))
        
        self.processing.add(model_id)
        
        logger.info(f"Building lineage for {model_id}")
        
        # Create node for this model
        node = ModelNode(
            model_id=model_id,
            model_name=model_id.split("/")[-1]
        )
        self.nodes[model_id] = node
        
        # Fetch metadata
        config, card_text = self.fetch_model_metadata(url)
        node.metadata = config or {}
        
        parents = set()
        
        # config.json
        if config:
            parent = self.extract_parent_from_config(config)
            if parent:
                logger.debug(f"Found parent from config: {parent}")
                parents.add(parent)
        
        # Model card text
        if card_text:
            card_parents = self.extract_parents_from_card(card_text, model_id)
            if card_parents:
                logger.debug(f"Found parents from card: {card_parents}")
                parents.update(card_parents)
        
        # Process parent models recursively if depth allows
        if depth > 0:
            for parent_id in parents:
                try:
                    # Skip if this would create a self-loop
                    if parent_id == model_id:
                        continue
                    
                    # Construct parent URL
                    parent_url = f"https://huggingface.co/{parent_id}"
                    parent_node = self.build_lineage(parent_url, depth - 1)
                    
                    # Add bidirectional relationship
                    if parent_id not in node.parents:
                        node.parents.append(parent_id)
                    if model_id not in parent_node.children:
                        parent_node.children.append(model_id)
                        
                except Exception as e:
                    logger.warning(f"Could not process parent {parent_id}: {e}")
                    # Still add as parent even if we can't recurse
                    if parent_id not in node.parents:
                        node.parents.append(parent_id)
        else:
            # Just record parent IDs without recursing
            node.parents.extend(parents)
        
        self.processing.discard(model_id)
        return node
    
    def get_lineage_dict(self, url: str, depth: int = 2) -> Dict:
        """
        Get lineage information as a dictionary suitable for JSON serialization.
        
        Returns:
            Dict with structure:
            {
                "model_id": str,
                "model_name": str,
                "parents": List[str],
                "children": List[str],
                "graph": {
                    "model_id": {
                        "parents": [...],
                        "children": [...]
                    },
                    ...
                }
            }
        """
        node = self.build_lineage(url, depth)
        
        # Build complete graph representation
        graph = {}
        for model_id, model_node in self.nodes.items():
            graph[model_id] = {
                "model_name": model_node.model_name,
                "parents": model_node.parents,
                "children": model_node.children
            }
        
        return {
            "model_id": node.model_id,
            "model_name": node.model_name,
            "parents": node.parents,
            "children": node.children,
            "graph": graph
        }