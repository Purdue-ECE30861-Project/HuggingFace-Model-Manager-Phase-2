from fastapi.testclient import TestClient
from src.__main__ import api_core
from src.api_test_returns import IS_MOCK_TESTING
from src.model.external_contracts import ArtifactMetadata, Artifact, ArtifactQuery, ArtifactRegEx, ArtifactData

IS_MOCK_TESTING = True

client = TestClient(api_core)


def test_get_artifacts():
    """Test GET /artifacts endpoint returns 5 ArtifactMetadata objects"""
    query_body = ArtifactQuery.test_value().model_dump()
    response = client.post("/artifacts?offset=0", json=query_body)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    
    # Verify each item matches the test_value structure
    for item in data:
        assert "name" in item
        assert "version" in item
        assert "id" in item
        assert "type" in item
        assert item["name"] == "Stirlitz"
        assert item["id"] == "48472749248"


def test_get_artifacts_by_name():
    """Test GET /artifact/byName/{name} endpoint returns 3 ArtifactMetadata objects"""
    response = client.post("/artifact/byName/test-artifact")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    
    # Verify each item matches the test_value structure
    for item in data:
        assert "name" in item
        assert "version" in item
        assert "id" in item
        assert "type" in item
        assert item["name"] == "Stirlitz"
        assert item["id"] == "48472749248"


def test_get_artifacts_by_regex():
    """Test GET /artifact/byRegEx endpoint returns 3 ArtifactMetadata objects"""
    regex_body = ArtifactRegEx.test_value().model_dump()
    response = client.post("/artifact/byRegEx", json=regex_body)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    
    # Verify each item matches the test_value structure
    for item in data:
        assert "name" in item
        assert "version" in item
        assert "id" in item
        assert "type" in item
        assert item["name"] == "Stirlitz"
        assert item["id"] == "48472749248"


def test_get_artifact():
    """Test GET /artifacts/{artifact_type}/{id} endpoint returns single Artifact"""
    response = client.get("/artifacts/model/48472749248")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify the structure matches Artifact with metadata and data
    assert "metadata" in data
    assert "data" in data
    
    # Check metadata
    metadata = data["metadata"]
    assert metadata["name"] == "Stirlitz"
    assert metadata["version"] == "0.0.7"
    assert metadata["id"] == "48472749248"
    assert metadata["type"] == "model"
    
    # Check data
    assert data["data"]["url"] == "http://IAmAGoon.com"


def test_update_artifact():
    """Test PUT /artifacts/{artifact_type}/{id} endpoint returns success message"""
    artifact_body = Artifact.test_value().model_dump()
    response = client.put("/artifacts/model/48472749248", json=artifact_body)
    
    assert response.status_code == 200
    # The response content should be set to the success message
    # Note: FastAPI Response.content is bytes, but in mock mode we set it as string
    # The actual response body may be empty since we return None


def test_delete_artifact():
    """Test DELETE /artifacts/{artifact_type}/{id} endpoint returns success"""
    response = client.delete("/artifacts/model/48472749248")
    
    assert response.status_code == 200
    # The response content should be set to the success message
    # Note: Similar to update, the response body may be empty since we return None


def test_register_artifact():
    """Test POST /artifacts/{artifact_type} endpoint returns Artifact"""
    data_body = ArtifactData.test_value().model_dump()
    response = client.post("/artifacts/model", json=data_body)
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify the structure matches Artifact with metadata and data
    assert "metadata" in data
    assert "data" in data
    
    # Check metadata
    metadata = data["metadata"]
    assert metadata["name"] == "Stirlitz"
    assert metadata["version"] == "0.0.7"
    assert metadata["id"] == "48472749248"
    assert metadata["type"] == "model"
    
    # Check data
    assert data["data"]["url"] == "http://IAmAGoon.com"