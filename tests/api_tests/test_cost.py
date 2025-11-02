from fastapi.testclient import TestClient
from src.__main__ import api_core
from src.api_test_returns import IS_MOCK_TESTING
from src.model.external_contracts import ArtifactCost

IS_MOCK_TESTING = True

client = TestClient(api_core)


def test_get_artifact_cost():
    """Test GET /artifact/{artifact_type}/{id}/cost endpoint returns ArtifactCost"""
    response = client.get("/artifact/model/48472749248/cost")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the structure matches ArtifactCost test_value
    # Based on the pattern, we expect the test_value structure
    assert isinstance(data, dict)
    
    # Test should verify the actual structure returned by ArtifactCost.test_value()
    # Add specific field validations based on what ArtifactCost.test_value() returns