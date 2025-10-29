from fastapi.testclient import TestClient
from src.__main__ import api_core


client = TestClient(api_core)


def test_accessor():
    pass