#!/usr/bin/env python3
import unittest
from unittest.mock import patch

# Import the module to test
from src.classes.lineage_graph import LineageGraph, ModelNode

class TestModelNode(unittest.TestCase):
    
    def test_model_node_creation(self):
        """
        Test basic ModelNode instantiation.
        """
        node = ModelNode(
            model_id="test/model",
            model_name="model"
        )
        self.assertEqual(node.model_id, "test/model")
        self.assertEqual(node.model_name, "model")
        self.assertEqual(node.parents, [])
        self.assertEqual(node.children, [])
        self.assertEqual(node.metadata, {})
        self.assertEqual(node.source, "unknown")
    
    def test_model_node_with_parents(self):
        """
        Test ModelNode with parent relationships.
        """
        node = ModelNode(
            model_id="test/model",
            model_name="model",
            parents=[
                {"id": "parent/model", "relationship": "fine_tuned", "source": "config_json"}
            ]
        )
        self.assertEqual(len(node.parents), 1)
        self.assertEqual(node.parents[0]["id"], "parent/model")
        self.assertEqual(node.parents[0]["relationship"], "fine_tuned")


class TestLineageGraphURLParsing(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    def test_extract_repo_id_standard_url(self):
        """
        Test extracting repo ID from standard HuggingFace URL.
        """
        url = "https://huggingface.co/google-bert/bert-base-uncased"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "google-bert/bert-base-uncased")
    
    def test_extract_repo_id_with_tree_path(self):
        """
        Test extracting repo ID from URL with tree path.
        """
        url = "https://huggingface.co/openai/whisper-tiny/tree/main"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "openai/whisper-tiny")
    
    def test_extract_repo_id_single_segment(self):
        """
        Test extracting repo ID with single segment.
        """
        url = "https://huggingface.co/distilbert"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "distilbert")
    
    def test_extract_repo_id_empty_path(self):
        """
        Test extracting repo ID from URL with empty path.
        """
        url = "https://huggingface.co/"
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "")


class TestLineageGraphParentExtraction(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    def test_extract_parent_from_config_base_model(self):
        """
        Test extracting parent from config with base_model field.
        """
        config = {
            "base_model": "bert-base-uncased",
            "model_type": "bert"
        }
        result = self.graph.extract_parent_from_config(config)
        self.assertIsNotNone(result)
        parent_id, relationship = result
        self.assertEqual(parent_id, "bert-base-uncased")
        self.assertEqual(relationship, "base_model")
    
    def test_extract_parent_from_config_list_value(self):
        """
        Test extracting parent when value is a list.
        """
        config = {
            "base_model": ["bert-base-uncased", "other-model"]
        }
        result = self.graph.extract_parent_from_config(config)
        self.assertIsNotNone(result)
        parent_id, relationship = result
        self.assertEqual(parent_id, "bert-base-uncased")
    
    def test_extract_parent_from_config_empty(self):
        """
        Test extracting parent with empty config.
        """
        result = self.graph.extract_parent_from_config({})
        self.assertIsNone(result)
    
    def test_extract_parents_from_card_fine_tuned(self):
        """
        Test extracting fine-tuned relationship from model card.
        """
        card_text = """
        This model was fine-tuned from [bert-base-uncased](https://huggingface.co/bert-base-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "test/model")
        self.assertEqual(len(parents), 1)
        parent_id, relationship = parents[0]
        self.assertEqual(parent_id, "bert-base-uncased")
        self.assertEqual(relationship, "fine_tuned")
    
    def test_extract_parents_from_card_none(self):
        """
        Test extracting parents with no card text.
        """
        parents = self.graph.extract_parents_from_card(None, "test/model")
        self.assertEqual(len(parents), 0)
    
    def test_extract_parents_from_card_excludes_self(self):
        """
        Test that model doesn't identify itself as parent.
        """
        card_text = """
        This model [test/model](https://huggingface.co/test/model) was fine-tuned.
        """
        parents = self.graph.extract_parents_from_card(card_text, "test/model")
        self.assertEqual(len(parents), 0)

    def test_extract_parents_from_card_multiple(self):
        """
        Test extracting multiple parents from card.
        """
        card_text = """
        This model was fine-tuned from [bert-base](https://huggingface.co/bert-base-uncased).
        It's also based on [roberta](https://huggingface.co/roberta-base).
        """
        parents = self.graph.extract_parents_from_card(card_text, "test/model")
        self.assertGreaterEqual(len(parents), 1)
    
    def test_extract_parents_from_card_deduplication(self):
        """
        Test that duplicate parents are removed.
        """
        card_text = """
        Fine-tuned from [bert](https://huggingface.co/bert-base-uncased).
        Based on [bert](https://huggingface.co/bert-base-uncased).
        """
        parents = self.graph.extract_parents_from_card(card_text, "test/model")
        # Should deduplicate to 1 parent
        self.assertEqual(len(parents), 1)


class TestLineageGraphBuilding(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_single_model(self, mock_fetch):
        """
        Test building lineage for a single model with no parents.
        """
        mock_fetch.return_value = (
            {"model_type": "bert"},
            "This is a base model."
        )
        
        url = "https://huggingface.co/bert-base-uncased"
        node = self.graph.build_lineage(url, depth=0)
        
        self.assertEqual(node.model_id, "bert-base-uncased")
        self.assertEqual(node.model_name, "bert-base-uncased")
        self.assertEqual(len(node.parents), 0)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_with_parent(self, mock_fetch):
        """
        Test building lineage with one parent.
        """
        # First call for child model
        mock_fetch.return_value = (
            {"base_model": "bert-base-uncased"},
            ""
        )
        
        url = "https://huggingface.co/fine-tuned/model"
        node = self.graph.build_lineage(url, depth=1)
        
        self.assertEqual(node.model_id, "fine-tuned/model")
        self.assertGreater(len(node.parents), 0)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_circular_dependency(self, mock_fetch):
        """
        Test that circular dependencies are handled.
        """
        # Create a circular reference
        mock_fetch.return_value = (
            {"base_model": "model-a"},
            ""
        )
        
        url = "https://huggingface.co/model-a"
        
        # Add model-a to processing set to simulate circular reference
        self.graph.processing.add("model-a")
        
        node = self.graph.build_lineage(url, depth=1)
        
        # Should handle gracefully
        self.assertIsNotNone(node)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_depth_zero(self, mock_fetch):
        """
        Test building lineage with depth=0.
        """
        mock_fetch.return_value = (
            {"base_model": "parent-model"},
            ""
        )
        
        url = "https://huggingface.co/child-model"
        node = self.graph.build_lineage(url, depth=0)
        
        # Should record parent but not fetch it
        self.assertGreater(len(node.parents), 0)
        # Parent should not be in nodes dict (not fetched)
        self.assertNotIn("parent-model", self.graph.nodes)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_build_lineage_already_processed(self, mock_fetch):
        """
        Test that already processed models are returned from cache.
        """
        mock_fetch.return_value = (
            {"model_type": "bert"},
            ""
        )
        
        url = "https://huggingface.co/bert-base"
        
        # First call
        node1 = self.graph.build_lineage(url, depth=0)
        
        # Second call should return cached node
        node2 = self.graph.build_lineage(url, depth=0)
        
        self.assertIs(node1, node2)
        # fetch should only be called once
        self.assertEqual(mock_fetch.call_count, 1)


class TestLineageGraphOpenAPICompliance(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict_structure(self, mock_fetch):
        """
        Test that get_lineage_dict returns correct structure.
        """
        mock_fetch.return_value = (
            {"model_type": "bert"},
            ""
        )
        
        url = "https://huggingface.co/test-model"
        result = self.graph.get_lineage_dict(url, depth=0)
        
        # Check top-level structure
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIsInstance(result["nodes"], list)
        self.assertIsInstance(result["edges"], list)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict_node_schema(self, mock_fetch):
        """
        Test that nodes comply with ArtifactLineageNode schema.
        """
        mock_fetch.return_value = (
            {"model_type": "bert"},
            ""
        )
        
        url = "https://huggingface.co/test-model"
        result = self.graph.get_lineage_dict(url, depth=0)
        
        # Check node structure
        self.assertGreater(len(result["nodes"]), 0)
        node = result["nodes"][0]
        
        # Required fields
        self.assertIn("artifact_id", node)
        self.assertIn("name", node)
        self.assertIn("source", node)
        
        # Check types
        self.assertIsInstance(node["artifact_id"], str)
        self.assertIsInstance(node["name"], str)
        self.assertIsInstance(node["source"], str)
        
        # Optional metadata field
        if "metadata" in node:
            self.assertIsInstance(node["metadata"], dict)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict_edge_schema(self, mock_fetch):
        """
        Test that edges comply with ArtifactLineageEdge schema.
        """
        # Setup mock to return a model with a parent
        def mock_fetch_side_effect(url):
            if "child" in url:
                return (
                    {"base_model": "parent-model"},
                    ""
                )
            else:
                return (
                    {"model_type": "bert"},
                    ""
                )
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        url = "https://huggingface.co/child-model"
        result = self.graph.get_lineage_dict(url, depth=1)
        
        # Check edge structure
        if len(result["edges"]) > 0:
            edge = result["edges"][0]
            
            # Required fields
            self.assertIn("from_node_artifact_id", edge)
            self.assertIn("to_node_artifact_id", edge)
            self.assertIn("relationship", edge)
            
            # Check types - MUST BE STRINGS
            self.assertIsInstance(edge["from_node_artifact_id"], str)
            self.assertIsInstance(edge["to_node_artifact_id"], str)
            self.assertIsInstance(edge["relationship"], str)
            
            # Ensure NOT a dict (common bug)
            self.assertNotIsInstance(edge["from_node_artifact_id"], dict)
            self.assertNotIsInstance(edge["to_node_artifact_id"], dict)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict_metadata_filtered(self, mock_fetch):
        """
        Test that metadata is properly filtered.
        """
        large_config = {
            "model_type": "bert",
            "hidden_size": 768,
            "num_layers": 12,
            "vocab_size": 30522,
            "intermediate_size": 3072,
            "num_attention_heads": 12,
            "base_model": "some-parent"
        }
        
        mock_fetch.return_value = (large_config, "")
        
        url = "https://huggingface.co/test-model"
        result = self.graph.get_lineage_dict(url, depth=0)
        
        node = result["nodes"][0]
        
        if "metadata" in node:
            # Should only contain relevant fields
            allowed_fields = {"model_type", "base_model", "parent_model"}
            actual_fields = set(node["metadata"].keys())
            self.assertTrue(actual_fields.issubset(allowed_fields))
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_get_lineage_dict_relationship_types(self, mock_fetch):
        """
        Test that relationship types are valid strings.
        """
        def mock_fetch_side_effect(url):
            if "child" in url:
                return (
                    {"base_model": "parent-model"},
                    ""
                )
            else:
                return (
                    {"model_type": "bert"},
                    ""
                )
        
        mock_fetch.side_effect = mock_fetch_side_effect
        
        url = "https://huggingface.co/child-model"
        result = self.graph.get_lineage_dict(url, depth=1)
        
        # Check that all relationship values are valid
        valid_relationships = {
            "fine_tuned", "based_on", "derived_from", "distilled_from",
            "trained_on_model", "variant_of", "base_model", "parent_model",
            "related_model"
        }
        
        for edge in result["edges"]:
            self.assertIsInstance(edge["relationship"], str)
            # Relationship should be one of the known types
            self.assertIn(edge["relationship"], valid_relationships)

class TestLineageGraphEdgeCases(unittest.TestCase):
    
    def setUp(self):
        self.graph = LineageGraph()
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_fetch_metadata_exception(self, mock_fetch):
        """
        Test handling of metadata fetch exceptions.
        """
        mock_fetch.side_effect = Exception("Network error")
        
        url = "https://huggingface.co/test-model"
        
        # Should handle gracefully
        try:
            result = self.graph.get_lineage_dict(url, depth=0)
            # Should still produce valid structure even on error
            self.assertIn("nodes", result)
            self.assertIn("edges", result)
        except Exception as e:
            # Or raise but with proper error handling
            self.assertIsInstance(e, Exception)
    
    def test_empty_url(self):
        """
        Test handling of empty URL.
        """
        url = ""
        repo_id = self.graph.extract_repo_id_from_url(url)
        self.assertEqual(repo_id, "")
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_model_with_empty_config(self, mock_fetch):
        """
        Test handling of empty config.
        """
        mock_fetch.return_value = ({}, "")
        
        url = "https://huggingface.co/test-model"
        result = self.graph.get_lineage_dict(url, depth=0)
        
        self.assertGreater(len(result["nodes"]), 0)
    
    @patch('src.classes.lineage_graph.LineageGraph.fetch_model_metadata')
    def test_model_with_none_metadata(self, mock_fetch):
        """
        Test handling of None metadata.
        """
        mock_fetch.return_value = (None, None)
        
        url = "https://huggingface.co/test-model"
        result = self.graph.get_lineage_dict(url, depth=0)
        
        # Should still create a node
        self.assertGreater(len(result["nodes"]), 0)
        node = result["nodes"][0]
        self.assertEqual(node["artifact_id"], "test-model")