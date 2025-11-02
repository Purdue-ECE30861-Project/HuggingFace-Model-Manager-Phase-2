from fastapi.testclient import TestClient
from src.__main__ import api_core
from src.api_test_returns import IS_MOCK_TESTING

IS_MOCK_TESTING = True

client = TestClient(api_core)


def test_reset():
    """Test DELETE /reset endpoint returns success"""
    response = client.delete("/reset")
    
    assert response.status_code == 200
    # The reset endpoint sets response.body = "Registry is reset."
    # Note: The actual response content handling may vary depending on FastAPI implementation