#!/usr/bin/env python3
import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse
from huggingface_hub import HfApi, hf_hub_download
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
    parents: List[Dict] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    source: str = "unknown"


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
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return parts[-1] if parts else ""
    
    def fetch_model_metadata(self, url: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Fetch config.json and model card for a given HuggingFace model.
        
        Returns:
            Tuple of (config_dict, card_text)
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
                logger.debug(f"Could not fetch model card for {model_id}: {e}")
                    
            return config, card_text
            
        except Exception as e:
            logger.warning(f"Error fetching metadata for {url}: {e}")
            return None, None
    
    def extract_parent_from_config(self, config: Dict | None) -> Optional[Tuple[str, str]]:
        """
        Extract parent model ID from config.json metadata.
        
        Returns:
            Tuple of (parent_id, relationship_type) or None
        """
        if not config:
            return None
        
        # Map config fields to relationship types
        parent_field_map = {
            "base_model": "base_model",
            "base_model_name_or_path": "base_model",
            "parent_model": "parent_model",
            "_name_or_path": "base_model",
            "model_name_or_path": "base_model"
        }
        
        for field, relationship in parent_field_map.items():
            if field in config:
                parent = config[field]
                if isinstance(parent, str) and parent.strip():
                    return (parent.strip(), relationship)
                if isinstance(parent, list) and len(parent) > 0:
                    return (parent[0], relationship)
        return None
    
    def extract_parents_from_card(self, card_text: str | None, model_id: str) -> List[Tuple[str, str]]:
        """
        Extract parent model references from model card text.
        
        Returns:
            List of tuples (parent_id, relationship_type)
        """
        if not card_text:
            return []
        
        parents = []
        
        # Relationship indicators mapping
        relationship_patterns = {
            'fine_tuned': ['fine-tuned', 'fine tuned', 'finetuned'],
            'based_on': ['based on', 'based off'],
            'derived_from': ['derived from', 'derived'],
            'distilled_from': ['distilled from', 'distilled version'],
            'trained_on_model': ['trained on', 'built on'],
            'variant_of': ['version of', 'variant of'],
        }
        
        # Markdown links with context - [text](url)
        link_pattern = r"\[([^\]]+)\]\(https://huggingface\.co/([a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_.-]+)?)/?\)"
        for match in re.finditer(link_pattern, card_text):
            parent_id = match.group(2)
            
            # Check if this link is in a parent-indicating context
            start_pos = max(0, match.start() - 100)
            context = card_text[start_pos:match.start()].lower()
            
            # Determine relationship type from context
            relationship = "related_model"  # default
            for rel_type, indicators in relationship_patterns.items():
                if any(indicator in context for indicator in indicators):
                    relationship = rel_type
                    break
            
            # Check if any parent indicators are present
            is_parent_link = relationship != "related_model"
            
            if is_parent_link and parent_id != model_id:
                parents.append((parent_id, relationship))
        
        # Direct HuggingFace URLs in context (backup)
        url_pattern = r"https://huggingface\.co/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)"
        for match in re.finditer(url_pattern, card_text):
            parent_id = match.group(1)
            
            # Exclude self and common non-model pages
            if parent_id == model_id or any(x in parent_id for x in ['datasets', 'spaces', 'docs', 'models']):
                continue
            
            # Check context for this URL
            start_pos = max(0, match.start() - 100)
            context = card_text[start_pos:match.start()].lower()
            
            relationship = "related_model"
            for rel_type, indicators in relationship_patterns.items():
                if any(indicator in context for indicator in indicators):
                    relationship = rel_type
                    break
            
            if relationship != "related_model":
                parents.append((parent_id, relationship))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_parents = []
        for parent_id, rel in parents:
            if parent_id not in seen:
                seen.add(parent_id)
                unique_parents.append((parent_id, rel))
        
        return unique_parents
    
    
    def build_lineage(self, url: str, depth: int = 2, source: str = "root") -> ModelNode:
        """
        Build lineage graph for a model by recursively analyzing parents.
        
        Args:
            url: HuggingFace model URL
            depth: How many levels up to trace (0 = just this model)
            source: How this node was discovered
        
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
            return self.nodes.get(model_id, ModelNode(
                model_id=model_id, 
                model_name=model_id.split("/")[-1],
                source=source
            ))
        
        self.processing.add(model_id)
        
        logger.info(f"Building lineage for {model_id}")
        
        # Create node for this model
        node = ModelNode(
            model_id=model_id,
            model_name=model_id.split("/")[-1],
            source=source
        )
        self.nodes[model_id] = node
        
        # Fetch metadata
        config, card_text = self.fetch_model_metadata(url)
        node.metadata = config or {}
        
        parents_with_relationships = []
        
        # Extract from config.json
        if config:
            parent_info = self.extract_parent_from_config(config)
            if parent_info:
                parent_id, relationship = parent_info
                logger.debug(f"Found parent from config: {parent_id} ({relationship})")
                parents_with_relationships.append((parent_id, relationship, "config_json"))
        
        # Extract from model card text
        if card_text:
            card_parents = self.extract_parents_from_card(card_text, model_id)
            for parent_id, relationship in card_parents:
                logger.debug(f"Found parent from card: {parent_id} ({relationship})")
                parents_with_relationships.append((parent_id, relationship, "model_card"))
        
        # Process parent models recursively if depth allows
        if depth > 0:
            for parent_id, relationship, discovery_source in parents_with_relationships:
                try:
                    # Skip if this would create a self-loop
                    if parent_id == model_id:
                        continue
                    
                    # Construct parent URL
                    parent_url = f"https://huggingface.co/{parent_id}"
                    parent_node = self.build_lineage(parent_url, depth - 1, discovery_source)
                    
                    # Add relationship info to parent list
                    parent_dict = {
                        "id": parent_id,
                        "relationship": relationship,
                        "source": discovery_source
                    }
                    if parent_dict not in node.parents:
                        node.parents.append(parent_dict)
                    
                    # Add bidirectional relationship
                    if model_id not in parent_node.children:
                        parent_node.children.append(model_id)
                        
                except Exception as e:
                    logger.warning(f"Could not process parent {parent_id}: {e}")
                    # Still add as parent even if we can't recurse
                    parent_dict = {
                        "id": parent_id,
                        "relationship": relationship,
                        "source": discovery_source
                    }
                    if parent_dict not in node.parents:
                        node.parents.append(parent_dict)
        else:
            # Just record parent IDs without recursing
            for parent_id, relationship, discovery_source in parents_with_relationships:
                parent_dict = {
                    "id": parent_id,
                    "relationship": relationship,
                    "source": discovery_source
                }
                node.parents.append(parent_dict)
        
        self.processing.discard(model_id)
        return node
    
    def get_lineage_dict(self, url: str, depth: int = 2) -> Dict:
        """
        Get lineage information as a dictionary compliant with OpenAPI ArtifactLineageGraph schema.
        
        Returns:
            Dict with structure:
            {
                "nodes": [
                    {
                        "artifact_id": str,
                        "name": str,
                        "source": str,
                        "metadata": dict (optional)
                    }
                ],
                "edges": [
                    {
                        "from_node_artifact_id": str,
                        "to_node_artifact_id": str,
                        "relationship": str
                    }
                ]
            }
        """
        # Build the lineage graph
        root_node = self.build_lineage(url, depth, source="root")
        
        # Build nodes array compliant with ArtifactLineageNode schema
        nodes = []
        edges = []
        
        for model_id, model_node in self.nodes.items():
            # Create node matching ArtifactLineageNode schema
            node_obj = {
                "artifact_id": model_id,
                "name": model_node.model_name,
                "source": model_node.source
            }
            
            # Add metadata if present (optional field)
            if model_node.metadata:
                # Include ONLY relevant metadata for lineage analysis
                filtered_metadata = {}
                
                # Only include these specific fields if they exist
                relevant_fields = ["model_type", "base_model", "parent_model"]
                for field in relevant_fields:
                    if field in model_node.metadata:
                        filtered_metadata[field] = model_node.metadata[field]
                
                # Only add metadata dict if we have relevant fields
                if filtered_metadata:
                    node_obj["metadata"] = filtered_metadata
            
            nodes.append(node_obj)
            
            # Create edges for each parent relationship
            for parent_info in model_node.parents:
                # Debug: ensure parent_info is a dict
                if not isinstance(parent_info, dict):
                    logger.warning(f"Unexpected parent_info format: {parent_info}")
                    continue
                
                # Extract fields - must be strings per OpenAPI spec
                parent_id = str(parent_info.get("id", ""))
                relationship = str(parent_info.get("relationship", "related_model"))
                
                if not parent_id:
                    logger.warning(f"Missing parent_id in parent_info: {parent_info}")
                    continue
                
                edge = {
                    "from_node_artifact_id": parent_id,  # Must be string
                    "to_node_artifact_id": model_id,     # Must be string
                    "relationship": relationship          # Must be string
                }
                edges.append(edge)
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def visualize_lineage(self, url: str, depth: int = 2) -> str:
        """
        Create a text-based visualization of the lineage graph.
        
        Returns:
            String representation of the tree structure
        """
        node = self.build_lineage(url, depth, source="root")
        
        lines = []
        
        def _add_tree(model_id: str, prefix: str = "", is_last: bool = True):
            """Recursively build tree visualization."""
            if model_id not in self.nodes:
                lines.append(f"{prefix}{'└── ' if is_last else '├── '}{model_id} (not loaded)")
                return
            
            node = self.nodes[model_id]
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{node.model_id}")
            
            # Add parents with relationship info
            if node.parents:
                new_prefix = prefix + ("    " if is_last else "│   ")
                for i, parent_info in enumerate(node.parents):
                    is_last_parent = (i == len(node.parents) - 1)
                    parent_id = parent_info["id"]
                    relationship = parent_info.get("relationship", "unknown")
                    lines.append(f"{new_prefix}{'└── ' if is_last_parent else '├── '}[{relationship}]")
                    _add_tree(parent_id, new_prefix + ("    " if is_last_parent else "│   "), True)
        
        lines.append(f"Lineage Graph for: {node.model_id}")
        lines.append("")
        _add_tree(node.model_id, "", True)
        
        return "\n".join(lines)