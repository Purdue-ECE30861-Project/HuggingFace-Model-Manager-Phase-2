import unittest
from unittest.mock import Mock, MagicMock
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.backend_server.classes.treescore import TreeScore
from src.contracts.artifact_contracts import (
    Artifact,
    ArtifactMetadata,
    ArtifactData,
    ArtifactType,
    ArtifactLineageGraph,
    ArtifactLineageNode,
    ArtifactLineageEdge
)
from src.contracts.model_rating import ModelRating
from src.backend_server.model.dependencies import DependencyBundle


class TestTreeScore(unittest.TestCase):
    """Test suite for TreeScore metric calculation."""

    def setUp(self):
        """Set up common test fixtures."""
        # Create a basic artifact for testing
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
        
        # Create a mock dependency bundle
        self.mock_dependency_bundle = Mock(spec=DependencyBundle)
        self.mock_db = Mock()
        self.mock_dependency_bundle.db = self.mock_db
        
        # Set up the router mocks
        self.mock_router_lineage = Mock()
        self.mock_router_rating = Mock()
        self.mock_db.router_lineage = self.mock_router_lineage
        self.mock_db.router_rating = self.mock_router_rating
        
        # Create test path
        self.test_path = Path("/tmp/test_model")
        
        # Create TreeScore instance
        self.metric = TreeScore(metric_weight=0.05)

    def test_metric_name(self):
        """Test that metric has correct name."""
        self.assertEqual(self.metric.metric_name, "tree_score")

    def test_successful_calculation_multiple_nodes(self):
        """Test successful calculation with multiple nodes that have ratings."""
        # Create lineage graph with 3 nodes
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(
                    artifact_id="dep-1",
                    name="dependency-1",
                    source="config_json",
                    metadata={}
                ),
                ArtifactLineageNode(
                    artifact_id="dep-2",
                    name="dependency-2",
                    source="model_card",
                    metadata={}
                ),
                ArtifactLineageNode(
                    artifact_id="dep-3",
                    name="dependency-3",
                    source="config_json",
                    metadata={}
                )
            ],
            edges=[
                ArtifactLineageEdge(
                    from_node_artifact_id="dep-1",
                    to_node_artifact_id="dep-2",
                    relationship="fine_tuning_dataset"
                )
            ]
        )
        
        # Create mock ratings with different scores
        mock_rating_1 = Mock(spec=ModelRating)
        mock_rating_1.net_score = 0.8
        
        mock_rating_2 = Mock(spec=ModelRating)
        mock_rating_2.net_score = 0.6
        
        mock_rating_3 = Mock(spec=ModelRating)
        mock_rating_3.net_score = 1.0
        
        # Configure mocks
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        
        # Return different ratings for different artifact IDs
        def get_rating_side_effect(artifact_id):
            if artifact_id == "dep-1":
                return mock_rating_1
            elif artifact_id == "dep-2":
                return mock_rating_2
            elif artifact_id == "dep-3":
                return mock_rating_3
            return None
        
        self.mock_router_rating.db_rating_get.side_effect = get_rating_side_effect
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        expected_score = (0.8 + 0.6 + 1.0) / 3.0  # Average of all three scores
        self.assertAlmostEqual(score, expected_score, places=5)
        
        # Verify correct methods were called
        self.mock_router_lineage.db_artifact_lineage.assert_called_once_with("test-model-123")
        self.assertEqual(self.mock_router_rating.db_rating_get.call_count, 3)

    def test_no_lineage_graph_returns_zero(self):
        """Test that None lineage graph returns 0.0."""
        # Configure mock to return None
        self.mock_router_lineage.db_artifact_lineage.return_value = None
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0)
        self.mock_router_lineage.db_artifact_lineage.assert_called_once_with("test-model-123")

    def test_empty_lineage_graph_returns_zero(self):
        """Test that lineage graph with no nodes returns 0.0."""
        # Create empty lineage graph
        empty_lineage_graph = ArtifactLineageGraph(nodes=[], edges=[])
        
        self.mock_router_lineage.db_artifact_lineage.return_value = empty_lineage_graph
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0)

    def test_nodes_without_ratings_returns_zero(self):
        """Test that nodes with no ratings return 0.0."""
        # Create lineage graph with nodes
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(
                    artifact_id="dep-1",
                    name="dependency-1",
                    source="config_json",
                    metadata={}
                ),
                ArtifactLineageNode(
                    artifact_id="dep-2",
                    name="dependency-2",
                    source="model_card",
                    metadata={}
                )
            ],
            edges=[]
        )
        
        # Configure mocks - all ratings return None
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = None
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0)

    def test_mixed_nodes_some_with_ratings(self):
        """Test nodes where only some have ratings."""
        # Create lineage graph
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(
                    artifact_id="dep-1",
                    name="dependency-1",
                    source="config_json",
                    metadata={}
                ),
                ArtifactLineageNode(
                    artifact_id="dep-2",
                    name="dependency-2",
                    source="model_card",
                    metadata={}
                ),
                ArtifactLineageNode(
                    artifact_id="dep-3",
                    name="dependency-3",
                    source="readme",
                    metadata={}
                )
            ],
            edges=[]
        )
        
        # Create ratings for only 2 of the 3 nodes
        mock_rating_1 = Mock(spec=ModelRating)
        mock_rating_1.net_score = 0.9
        
        mock_rating_3 = Mock(spec=ModelRating)
        mock_rating_3.net_score = 0.7
        
        # Configure mocks
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        
        def get_rating_side_effect(artifact_id):
            if artifact_id == "dep-1":
                return mock_rating_1
            elif artifact_id == "dep-2":
                return None  # No rating for dep-2
            elif artifact_id == "dep-3":
                return mock_rating_3
            return None
        
        self.mock_router_rating.db_rating_get.side_effect = get_rating_side_effect
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify - should average only the 2 nodes with ratings
        expected_score = (0.9 + 0.7) / 2.0
        self.assertAlmostEqual(score, expected_score, places=5)

    def test_single_node_with_rating(self):
        """Test single node in lineage graph."""
        # Create lineage graph with single node
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(
                    artifact_id="dep-1",
                    name="dependency-1",
                    source="config_json",
                    metadata={}
                )
            ],
            edges=[]
        )
        
        mock_rating = Mock(spec=ModelRating)
        mock_rating.net_score = 0.75
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = mock_rating
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.75)

    def test_all_perfect_scores(self):
        """Test when all dependencies have perfect scores."""
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(artifact_id=f"dep-{i}", name=f"dep-{i}", 
                                  source="config_json", metadata={})
                for i in range(5)
            ],
            edges=[]
        )
        
        mock_rating = Mock(spec=ModelRating)
        mock_rating.net_score = 1.0
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = mock_rating
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 1.0)

    def test_all_zero_scores(self):
        """Test when all dependencies have zero scores."""
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(artifact_id=f"dep-{i}", name=f"dep-{i}",
                                  source="config_json", metadata={})
                for i in range(3)
            ],
            edges=[]
        )
        
        mock_rating = Mock(spec=ModelRating)
        mock_rating.net_score = 0.0
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = mock_rating
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.0)

    def test_exception_handling(self):
        """Test that exceptions are caught and return 0.0."""
        # Configure mock to raise an exception
        self.mock_router_lineage.db_artifact_lineage.side_effect = Exception("Database error")
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify - should return 0.0 on exception
        self.assertEqual(score, 0.0)

    def test_score_bounds(self):
        """Test that returned score is always between 0.0 and 1.0."""
        # Test with various rating values
        test_cases = [
            ([0.1, 0.2, 0.3], 0.2),
            ([0.5, 0.5, 0.5], 0.5),
            ([0.0, 0.5, 1.0], 0.5),
            ([0.99, 0.98, 0.97], 0.98)
        ]
        
        for net_scores, expected in test_cases:
            with self.subTest(net_scores=net_scores):
                # Create lineage graph
                lineage_graph = ArtifactLineageGraph(
                    nodes=[
                        ArtifactLineageNode(artifact_id=f"dep-{i}", name=f"dep-{i}",
                                          source="config_json", metadata={})
                        for i in range(len(net_scores))
                    ],
                    edges=[]
                )
                
                self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
                
                # Create side effect that returns different ratings
                def get_rating(artifact_id):
                    idx = int(artifact_id.split('-')[1])
                    mock_rating = Mock(spec=ModelRating)
                    mock_rating.net_score = net_scores[idx]
                    return mock_rating
                
                self.mock_router_rating.db_rating_get.side_effect = get_rating
                
                # Execute
                score = self.metric.calculate_metric_score(
                    self.test_path,
                    self.test_artifact,
                    self.mock_dependency_bundle
                )
                
                # Verify score is in bounds
                self.assertGreaterEqual(score, 0.0)
                self.assertLessEqual(score, 1.0)
                self.assertAlmostEqual(score, expected, places=5)

    def test_metric_weight_property(self):
        """Test that metric weight is properly set."""
        metric = TreeScore(metric_weight=0.05)
        self.assertEqual(metric.get_weight(), 0.05)
        
        metric2 = TreeScore(metric_weight=0.1)
        self.assertEqual(metric2.get_weight(), 0.1)

    def test_run_score_calculation(self):
        """Test the full run_score_calculation method (inherited from MetricStd)."""
        # Create a simple lineage graph
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(artifact_id="dep-1", name="dep-1",
                                  source="config_json", metadata={})
            ],
            edges=[]
        )
        
        mock_rating = Mock(spec=ModelRating)
        mock_rating.net_score = 0.8
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = mock_rating
        
        # Set parameters first
        self.metric.set_params(self.test_path, self.test_artifact, self.mock_dependency_bundle)
        
        # Execute run_score_calculation
        metric_name, latency, raw_score, weighted_score = self.metric.run_score_calculation()
        
        # Verify
        self.assertEqual(metric_name, "tree_score")
        self.assertIsInstance(latency, float)
        self.assertGreater(latency, 0)  # Should have some execution time
        self.assertEqual(raw_score, 0.8)
        self.assertEqual(weighted_score, 0.8 * 0.05)  # raw_score * weight


class TestTreeScoreEdgeCases(unittest.TestCase):
    """Additional edge case tests for TreeScore."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_artifact = Artifact(
            metadata=ArtifactMetadata(
                name="edge-case-model",
                id="edge-123",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://huggingface.co/test/model",
                download_url="https://example.com/download"
            )
        )
        
        self.mock_dependency_bundle = Mock(spec=DependencyBundle)
        self.mock_db = Mock()
        self.mock_dependency_bundle.db = self.mock_db
        self.mock_router_lineage = Mock()
        self.mock_router_rating = Mock()
        self.mock_db.router_lineage = self.mock_router_lineage
        self.mock_db.router_rating = self.mock_router_rating
        
        self.test_path = Path("/tmp/test")
        self.metric = TreeScore(metric_weight=0.05)

    def test_very_large_lineage_graph(self):
        """Test with a large number of dependencies."""
        # Create 100 nodes
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(artifact_id=f"dep-{i:03d}", name=f"dep-{i:03d}",
                                  source="config_json", metadata={})
                for i in range(100)
            ],
            edges=[]
        )
        
        mock_rating = Mock(spec=ModelRating)
        mock_rating.net_score = 0.5
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        self.mock_router_rating.db_rating_get.return_value = mock_rating
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        self.assertEqual(score, 0.5)
        self.assertEqual(self.mock_router_rating.db_rating_get.call_count, 100)

    def test_floating_point_precision(self):
        """Test that floating point arithmetic is handled correctly."""
        lineage_graph = ArtifactLineageGraph(
            nodes=[
                ArtifactLineageNode(artifact_id=f"dep-{i}", name=f"dep-{i}",
                                  source="config_json", metadata={})
                for i in range(3)
            ],
            edges=[]
        )
        
        # Use scores that don't divide evenly
        net_scores = [0.333333, 0.666666, 0.999999]
        
        self.mock_router_lineage.db_artifact_lineage.return_value = lineage_graph
        
        def get_rating(artifact_id):
            idx = int(artifact_id.split('-')[1])
            mock_rating = Mock(spec=ModelRating)
            mock_rating.net_score = net_scores[idx]
            return mock_rating
        
        self.mock_router_rating.db_rating_get.side_effect = get_rating
        
        # Execute
        score = self.metric.calculate_metric_score(
            self.test_path,
            self.test_artifact,
            self.mock_dependency_bundle
        )
        
        # Verify
        expected = sum(net_scores) / len(net_scores)
        self.assertAlmostEqual(score, expected, places=5)


if __name__ == "__main__":
    unittest.main()
