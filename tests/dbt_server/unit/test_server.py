from dbt_server.server import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_check():
    response = client.get("/check")
    assert response.status_code == 200
    assert response.json() == {"response": "Running dbt-server on port 8001"}
