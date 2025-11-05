from fastapi.testclient import TestClient
from src.__main__ import api_core
from src.api_test_returns import IS_MOCK_TESTING
from src.model.external_contracts import ModelRating

IS_MOCK_TESTING = True

client = TestClient(api_core)


def test_rate_model():
    """Test GET /artifact/model/{id}/rate endpoint returns ModelRating"""
    response = client.get("/artifact/model/48472749248/rate")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the structure matches ModelRating test_value
    assert isinstance(data, dict)
    
    # Test should verify the actual structure returned by ModelRating.test_value()
    # Add specific field validations based on what ModelRating.test_value() returns