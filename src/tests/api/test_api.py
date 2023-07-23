def test_probe_live__responds(client):
    response = client.get("/probe/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
