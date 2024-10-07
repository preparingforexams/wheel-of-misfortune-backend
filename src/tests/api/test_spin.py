from http import HTTPStatus

import pytest

from tests.bearer_auth import BearerAuth


@pytest.fixture(autouse=True)
def setup(client, internal_auth, wheel_auth):
    client.post(
        "/drink",
        auth=internal_auth,
        params=dict(name="Example"),
    ).raise_for_status()
    try:
        yield
    finally:
        responses = [
            client.put("/unlock", auth=wheel_auth),
            client.delete(
                "/drink",
                auth=internal_auth,
                params=dict(drink_id=None),
            ),
        ]
        for response in responses:
            response.raise_for_status()


@pytest.mark.xfail(reason="Bug in FastAPI")
def test_spin__no_auth(client):
    response = client.post(
        "/spin",
        params=dict(speed=1.0),
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_spin__invalid_auth(client):
    response = client.post(
        "/spin",
        auth=BearerAuth("invalid"),
        params=dict(speed=1.0),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_spin__internal_auth(client, internal_auth):
    response = client.post(
        "/spin",
        auth=internal_auth,
        params=dict(speed=1.0),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_spin__wheel_auth(client, internal_auth):
    response = client.post(
        "/spin",
        auth=internal_auth,
        params=dict(speed=1.0),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_spin__success(client, spin_auth_factory):
    response = client.post(
        "/spin",
        auth=spin_auth_factory(),
        params=dict(speed=1.0),
    )

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_spin__twice_fails(client, spin_auth_factory):
    auth = spin_auth_factory()
    response = client.post(
        "/spin",
        auth=auth,
        params=dict(speed=1.0),
    )
    assert response.status_code == HTTPStatus.NO_CONTENT

    second_response = client.post(
        "/spin",
        auth=auth,
        params=dict(speed=1.0),
    )
    assert second_response.status_code == HTTPStatus.CONFLICT