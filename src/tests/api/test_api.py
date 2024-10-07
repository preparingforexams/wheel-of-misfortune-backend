def test_docs_redirect(client):
    response = client.get("/")
    assert response.is_redirect
    assert response.has_redirect_location
    assert response.headers["Location"] == "/docs"


def test_probe_live__responds(client):
    response = client.get("/probe/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
