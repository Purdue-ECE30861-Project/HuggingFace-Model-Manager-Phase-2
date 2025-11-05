from fastapi.testclient import TestClient
from src.__main__ import api_core
from src.api_test_returns import IS_MOCK_TESTING
from src.model.external_contracts import ArtifactLineageGraph

IS_MOCK_TESTING = True

client = TestClient(api_core)


def test_get_model_lineage():
    """Test GET /artifact/model/{id}/lineage endpoint returns ArtifactLineageGraph"""
    response = client.get("/artifact/model/48472749248/lineage")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the structure matches ArtifactLineageGraph test_value
    assert isinstance(data, dict)
    
    # Test should verify the actual structure returned by ArtifactLineageGraph.test_value()
    # Add specific field validations based on what ArtifactLineageGraph.test_value() returns