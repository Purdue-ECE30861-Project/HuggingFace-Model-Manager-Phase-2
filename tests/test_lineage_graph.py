#!/usr/bin/env python3
import unittest
from unittest.mock import patch
import json
import tempfile
import os
from src.classes.lineage_graph import LineageGraph, ModelNode


class TestModelNode(unittest.TestCase):
 
    def test_model_node_creation(self):
        """
        Test basic ModelNode creation.
        """
        node = ModelNode(
            model_id="bert-base-uncased",
            model_name="bert-base-uncased"
        )
        self.assertEqual(node.model_id, "bert-base-uncased")
        self.assertEqual(node.model_name, "bert-base-uncased")
        self.assertEqual(node.parents, [])
        self.assertEqual(node.children, [])
        self.assertEqual(node.metadata, {})
    
    def test_model_node_with_relationships(self):
        """
        Test ModelNode with parent and child relationships.
        """
        node = ModelNode(
            model_id="fine-tuned-bert",
            model_name="fine-tuned-bert",
            parents=["bert-base-uncased"],
            children=["further-tuned-bert"]
        )
        self.assertEqual(len(node.parents), 1)
        self.assertEqual(len(node.children), 1)
        self.assertIn("bert-base-uncased", node.parents)
        self.assertIn("further-tuned-bert", node.children)


class TestLineageGraphURLParsing(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    def test_extract_repo_id_standard_url(self):
        """
        Test extraction from standard HuggingFace URL.
        """
        url = "https://huggingface.co/bert-base-uncased"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "bert-base-uncased")
    
    def test_extract_repo_id_with_org(self):
        """
        Test extraction from URL with organization.
        """
        url = "https://huggingface.co/google/bert-base-uncased"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "bert-base-uncased")
    
    def test_extract_repo_id_trailing_slash(self):
        """
        Test extraction with trailing slash.
        """
        url = "https://huggingface.co/bert-base-uncased/"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "bert-base-uncased")


class TestConfigParentExtraction(unittest.TestCase):
    """
    Test parent extraction from config.json.
    """
    
    def setUp(self):
        self.graph = LineageGraph()
    
    def test_extract_parent_base_model(self):
        """
        Test extraction using base_model field.
        """
        config = {"base_model": "bert-base-uncased"}
        parent = self.graph.extract_parent_from_config(config)
        self.assertEqual(parent, "bert-base-uncased")
    
    def test_extract_parent_from_list(self):
        """
        Test extraction when parent is in a list.
        """
        config = {"base_model": ["bert-base-uncased", "another-model"]}
        parent = self.graph.extract_parent_from_config(config)
        self.assertEqual(parent, "bert-base-uncased")
    
    def test_extract_parent_empty_config(self):
        """
        Test with empty config.
        """
        config = {}
        parent = self.graph.extract_parent_from_config(config)
        self.assertIsNone(parent)


class TestModelCardParentExtraction(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    def test_extract_parents_fine_tuned_markdown_link(self):
        """
        Test extraction from 'fine-tuned from' with markdown link.
        """
        card_text = """
        # My Model
        
        This model is fine-tuned from [BERT](https://huggingface.co/bert-base-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertIn("bert-base-uncased", parents)
    
    def test_extract_parents_based_on(self):
        """
        Test extraction from 'based on' context.
        """
        card_text = """
        This model is based on [GPT-2](https://huggingface.co/gpt2) architecture.
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertIn("gpt2", parents)
    
    def test_extract_parents_distilled(self):
        """
        Test extraction from 'distilled from' context.
        """
        card_text = """
        Distilled from [BERT-large](https://huggingface.co/bert-large-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertIn("bert-large-uncased", parents)
    
    def test_extract_parents_multiple(self):
        """
        Test extraction of multiple parents.
        """
        card_text = """
        Fine-tuned from [BERT](https://huggingface.co/bert-base-uncased).
        Uses techniques from [RoBERTa](https://huggingface.co/roberta-base).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertIn("bert-base-uncased", parents)
        self.assertIn("roberta-base", parents)
    
    def test_extract_parents_with_org(self):
        """
        Test extraction with organization in URL.
        """
        card_text = """
        Based on [LLaMA](https://huggingface.co/meta-llama/Llama-2-7b).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertIn("meta-llama/Llama-2-7b", parents)
    
    def test_extract_parents_empty_card(self):
        """
        Test with empty card text.
        """
        parents = self.graph.extract_parents_from_card("", "my-model")
        self.assertEqual(parents, [])
    
    def test_extract_parents_exclude_self(self):
        """
        Test that self-references are excluded.
        """
        card_text = """
        This is [my-model](https://huggingface.co/my-model).
        Based on [bert](https://huggingface.co/bert-base-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertNotIn("my-model", parents)
        self.assertIn("bert-base-uncased", parents)

    def test_extract_parents_deduplication(self):
        """
        Test that duplicate parents are removed.
        """
        card_text = """
        Fine-tuned from [BERT](https://huggingface.co/bert-base-uncased).
        Based on [BERT](https://huggingface.co/bert-base-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "my-model")
        self.assertEqual(parents.count("bert-base-uncased"), 1)


class TestLineageGraphConstruction(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.hf_hub_download')
    def test_fetch_model_metadata_success(self, mock_download):
        """
        Test successful metadata fetching.
        """
        # Mock config.json
        config_data = {"base_model": "bert-base-uncased"}
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(config_data, f)
            config_path = f.name
        
        # Mock README.md
        readme_text = "# Model\nFine-tuned from BERT"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            f.write(readme_text)
            readme_path = f.name
        
        try:
            mock_download.side_effect = [config_path, readme_path]
            
            config, card = self.graph.fetch_model_metadata(
                "https://huggingface.co/my-model"
            )
            
            self.assertIsNotNone(config)
            self.assertEqual(config["base_model"], "bert-base-uncased")
            self.assertIsNotNone(card)
            self.assertIn("Fine-tuned from BERT", card)
        finally:
            os.unlink(config_path)
            os.unlink(readme_path)
    
    @patch('src.classes.lineage_graph.hf_hub_download')
    def test_fetch_model_metadata_missing_config(self, mock_download):
        """
        Test metadata fetching when config.json is missing.
        """
        mock_download.side_effect = Exception("File not found")
        
        config, card = self.graph.fetch_model_metadata(
            "https://huggingface.co/my-model"
        )
        
        self.assertIsNone(config)
        self.assertIsNone(card)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_single_model(self, mock_fetch):
        """
        Test building lineage for a model with no parents.
        """
        mock_fetch.return_value = ({}, "# Model\nNo parents")
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=1
        )
        
        self.assertEqual(node.model_id, "my-model")
        self.assertEqual(node.parents, [])
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_with_parent(self, mock_fetch):
        """
        Test building lineage with one parent.
        """
        def fetch_side_effect(url):
            if "my-model" in url:
                return (
                    {"base_model": "bert-base-uncased"},
                    "Fine-tuned from BERT"
                )
            else:
                return ({}, "Base model")
        
        mock_fetch.side_effect = fetch_side_effect
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=1
        )
        
        self.assertEqual(node.model_id, "my-model")
        self.assertIn("bert-base-uncased", node.parents)
        self.assertIn("bert-base-uncased", self.graph.nodes)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_depth_zero(self, mock_fetch):
        """
        Test building lineage with depth=0 (no recursion).
        """
        mock_fetch.return_value = (
            {"base_model": "bert-base-uncased"},
            "Fine-tuned from BERT"
        )
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=0
        )
        
        self.assertEqual(node.model_id, "my-model")
        self.assertIn("bert-base-uncased", node.parents)
        # Parent should not be in nodes (not recursively fetched)
        self.assertNotIn("bert-base-uncased", self.graph.nodes)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_circular_dependency(self, mock_fetch):
        """
        Test handling of circular dependencies.
        """
        def fetch_side_effect(url):
            if "model-a" in url:
                return ({"base_model": "model-b"}, "")
            else:
                return ({"base_model": "model-a"}, "")
        
        mock_fetch.side_effect = fetch_side_effect
        
        # Should not cause infinite recursion
        node = self.graph.build_lineage(
            "https://huggingface.co/model-a",
            depth=2
        )
        
        self.assertEqual(node.model_id, "model-a")
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_self_reference(self, mock_fetch):
        """
        Test handling of self-references.
        """
        mock_fetch.return_value = (
            {"base_model": "my-model"},
            "Model references itself"
        )
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=1
        )
        
        # Should not create self-loop
        self.assertNotIn("my-model", node.parents)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_multi_level(self, mock_fetch):
        """
        Test building multi-level lineage.
        """
        def fetch_side_effect(url):
            if "model-c" in url:
                return ({"base_model": "model-b"}, "")
            elif "model-b" in url:
                return ({"base_model": "model-a"}, "")
            else:
                return ({}, "Base model")
        
        mock_fetch.side_effect = fetch_side_effect
        
        node = self.graph.build_lineage(
            "https://huggingface.co/model-c",
            depth=2
        )
        
        self.assertEqual(node.model_id, "model-c")
        self.assertIn("model-b", node.parents)
        self.assertIn("model-b", self.graph.nodes)
        self.assertIn("model-a", self.graph.nodes["model-b"].parents)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_bidirectional_relationships(self, mock_fetch):
        """
        Test that parent-child relationships are bidirectional.
        """
        def fetch_side_effect(url):
            if "child" in url:
                return ({"base_model": "parent"}, "")
            else:
                return ({}, "")
        
        mock_fetch.side_effect = fetch_side_effect
        
        child_node = self.graph.build_lineage(
            "https://huggingface.co/child",
            depth=1
        )
        
        parent_node = self.graph.nodes.get("parent")
        self.assertIsNotNone(parent_node)
        self.assertIn("parent", child_node.parents)
        self.assertIn("child", parent_node.children)


class TestLineageGraphOutput(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict(self, mock_fetch):
        """
        Test dictionary output of lineage.
        """
        mock_fetch.return_value = (
            {"base_model": "parent"},
            ""
        )
        
        result = self.graph.get_lineage_dict(
            "https://huggingface.co/my-model",
            depth=1
        )
        
        self.assertIn("model_id", result)
        self.assertIn("model_name", result)
        self.assertIn("parents", result)
        self.assertIn("children", result)
        self.assertIn("graph", result)
        self.assertEqual(result["model_id"], "my-model")
        self.assertIsInstance(result["graph"], dict)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_visualize_lineage(self, mock_fetch):
        """
        Test text visualization of lineage.
        """
        def fetch_side_effect(url):
            if "child" in url:
                return ({"base_model": "parent"}, "")
            else:
                return ({}, "")
        
        mock_fetch.side_effect = fetch_side_effect
        
        visualization = self.graph.visualize_lineage(
            "https://huggingface.co/child",
            depth=1
        )
        
        self.assertIsInstance(visualization, str)
        self.assertIn("child", visualization)
        self.assertIn("parent", visualization)
        self.assertIn("└──", visualization)


class TestLineageGraphEdgeCases(unittest.TestCase):
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_empty_metadata(self, mock_fetch):
        """
        Test handling of empty metadata.
        """
        mock_fetch.return_value = (None, None)
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=0
        )
        
        self.assertEqual(node.model_id, "my-model")
        self.assertEqual(node.parents, [])
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_malformed_config(self, mock_fetch):
        """
        Test handling of malformed config data.
        """
        mock_fetch.return_value = (
            {"base_model": None},
            ""
        )
        
        node = self.graph.build_lineage(
            "https://huggingface.co/my-model",
            depth=0
        )
        
        self.assertEqual(node.model_id, "my-model")
    
    def test_already_processed_model(self):
        """
        Test that already processed models are returned from cache.
        """
        # Create a node manually
        existing_node = ModelNode(
            model_id="cached-model",
            model_name="cached-model"
        )
        self.graph.nodes["cached-model"] = existing_node
        
        # Build lineage should return cached node
        node = self.graph.build_lineage(
            "https://huggingface.co/cached-model",
            depth=1
        )
        
        self.assertIs(node, existing_node)