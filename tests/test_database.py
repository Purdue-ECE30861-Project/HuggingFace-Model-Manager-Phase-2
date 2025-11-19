from src.utils.database import *
from unittest import TestCase
from src.controller.api_types import ModelRating, SizeScore
from pydantic import HttpUrl


class TestDatabaseAccessor(TestCase):
    def setUp(self):
        # Create three test models with different characteristics
        size_score1 = SizeScore(
            raspberry_pi=0.7,
            jetson_nano=0.8,
            desktop_pc=0.9,
            aws_server=1.0
        )
        
        rating1 = ModelRating(
            name="bert-base",
            category="MODEL",
            net_score=0.85,
            net_score_latency=10.5,
            ramp_up_time=0.9,
            ramp_up_time_latency=2.0,
            bus_factor=0.8,
            bus_factor_latency=3.0,
            performance_claims=0.85,
            performance_claims_latency=4.0,
            license=1.0,
            license_latency=1.0,
            dataset_and_code_score=0.9,
            dataset_and_code_score_latency=5.0,
            dataset_quality=0.85,
            dataset_quality_latency=4.0,
            code_quality=0.9,
            code_quality_latency=3.0,
            reproducibility=0.8,
            reproducibility_latency=5.0,
            reviewedness=0.9,
            reviewedness_latency=2.0,
            tree_score=0.85,
            tree_score_latency=3.0,
            size_score=size_score1,
            size_score_latency=1.0
        )

        self.model1 = ModelData(
            model_url=HttpUrl("https://huggingface.co/bert-base-uncased"),
            dataset_url=HttpUrl("https://huggingface.co/datasets/bert-base-dataset"),
            codebase_url=HttpUrl("https://github.com/google-research/bert"),
            rating=rating1
        )

        # Second model with different scores
        size_score2 = SizeScore(
            raspberry_pi=0.5,
            jetson_nano=0.6,
            desktop_pc=0.8,
            aws_server=0.9
        )
        
        rating2 = ModelRating(
            name="gpt2-small",
            category="MODEL",
            net_score=0.80,
            net_score_latency=12.0,
            ramp_up_time=0.85,
            ramp_up_time_latency=2.5,
            bus_factor=0.75,
            bus_factor_latency=3.5,
            performance_claims=0.80,
            performance_claims_latency=4.5,
            license=0.95,
            license_latency=1.2,
            dataset_and_code_score=0.85,
            dataset_and_code_score_latency=5.5,
            dataset_quality=0.80,
            dataset_quality_latency=4.5,
            code_quality=0.85,
            code_quality_latency=3.5,
            reproducibility=0.75,
            reproducibility_latency=5.5,
            reviewedness=0.85,
            reviewedness_latency=2.5,
            tree_score=0.80,
            tree_score_latency=3.5,
            size_score=size_score2,
            size_score_latency=1.5
        )

        self.model2 = ModelData(
            model_url=HttpUrl("https://huggingface.co/gpt2"),
            dataset_url=HttpUrl("https://huggingface.co/datasets/openai-gpt2"),
            codebase_url=HttpUrl("https://github.com/openai/gpt-2"),
            rating=rating2
        )

        # Third model with minimal URLs
        size_score3 = SizeScore(
            raspberry_pi=0.9,
            jetson_nano=0.95,
            desktop_pc=1.0,
            aws_server=1.0
        )
        
        rating3 = ModelRating(
            name="tiny-bert",
            category="MODEL",
            net_score=0.90,
            net_score_latency=8.0,
            ramp_up_time=0.95,
            ramp_up_time_latency=1.5,
            bus_factor=0.85,
            bus_factor_latency=2.5,
            performance_claims=0.90,
            performance_claims_latency=3.5,
            license=1.0,
            license_latency=0.8,
            dataset_and_code_score=0.95,
            dataset_and_code_score_latency=4.0,
            dataset_quality=0.90,
            dataset_quality_latency=3.5,
            code_quality=0.95,
            code_quality_latency=2.5,
            reproducibility=0.85,
            reproducibility_latency=4.5,
            reviewedness=0.95,
            reviewedness_latency=1.5,
            tree_score=0.90,
            tree_score_latency=2.5,
            size_score=size_score3,
            size_score_latency=0.8
        )

        self.model3 = ModelData(
            model_url=HttpUrl("https://huggingface.co/prajjwal1/bert-tiny"),
            dataset_url=None,
            codebase_url=None,
            rating=rating3
        )

    def test_add_and_retrieve(self):
        # Initialize in-memory database
        accessor = SQLAccessor("sqlite:///test.db")
        
        # Add all models to database
        accessor.add_to_db(self.model1)
        accessor.add_to_db(self.model2)
        accessor.add_to_db(self.model3)
        
        # Test retrieving by name
        retrieved_model = accessor.get_by_name("bert-base")
        self.assertIsNotNone(retrieved_model, "Model should be retrieved successfully")
        if retrieved_model:
            self.assertEqual(retrieved_model.rating.name, "bert-base")
            self.assertEqual(retrieved_model.rating.net_score, 0.85)
    
    def test_in_db_check(self):
        accessor = SQLAccessor()
        accessor.add_to_db(self.model1)
        accessor.add_to_db(self.model2)
        accessor.add_to_db(self.model3)

        self.assertTrue(accessor.is_in_db("bert-base"))
        self.assertTrue(accessor.is_in_db("gpt2-small"))
        self.assertTrue(accessor.is_in_db("tiny-bert"))
        self.assertFalse(accessor.is_in_db("nonexistent-model"))
    
    def test_get_all(self):
        accessor = SQLAccessor()
        accessor.add_to_db(self.model1)
        accessor.add_to_db(self.model2)
        accessor.add_to_db(self.model3)
        # Test getting all models
        all_models = accessor.get_all()
        self.assertIsNotNone(all_models, "Should get list of all models")
        if all_models:
            self.assertEqual(len(all_models), 3)
    
    def test_get_by_regex(self):
        accessor = SQLAccessor()
        accessor.add_to_db(self.model1)
        accessor.add_to_db(self.model2)
        accessor.add_to_db(self.model3)
        # Test regex search
        bert_models = accessor.get_by_regex(r".*bert.*")
        self.assertIsNotNone(bert_models, "Should find BERT models")
        if bert_models: 
            self.assertEqual(len(bert_models), 2)  # Should find bert-base and tiny-bert
        
        gpt_models = accessor.get_by_regex(r".*gpt.*")
        self.assertIsNotNone(gpt_models, "Should find GPT models")
        if gpt_models:
            self.assertEqual(len(gpt_models), 1)  # Should find gpt2-small
