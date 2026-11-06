"""Public beta opt-in contract; no Firebase or network calls."""
import hashlib
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import AlreadyExists
from app.database.firebase_db import FirebaseManager


def test_signup_normalizes_and_stores(unauthed_client, firebase_mock):
    response = unauthed_client.post('/beta-signups', json={
        'email': '  Person@Example.COM  ', 'consent': True,
    })
    assert response.status_code == 200
    firebase_mock.create_beta_signup.assert_called_once_with('person@example.com')


@pytest.mark.parametrize('payload', [
    {'email': 'not-an-email', 'consent': True},
    {'email': 'a..b@example.com', 'consent': True},
    {'email': 'a' * 65 + '@example.com', 'consent': True},
    {'email': 'person@example.com', 'consent': False},
    {'email': 'person@example.com', 'consent': 'true'},
    {'email': 'person@example.com'},
])
def test_invalid_signup(unauthed_client, firebase_mock, payload):
    assert unauthed_client.post('/beta-signups', json=payload).status_code == 422
    firebase_mock.create_beta_signup.assert_not_called()


def test_honeypot_returns_same_success_without_write(unauthed_client, firebase_mock):
    payload = {'email': 'person@example.com', 'consent': True}
    normal = unauthed_client.post('/beta-signups', json=payload)
    firebase_mock.create_beta_signup.reset_mock()
    trapped = unauthed_client.post('/beta-signups', json={**payload, 'website': 'spam'})
    assert trapped.status_code == normal.status_code == 200
    assert trapped.json() == normal.json()
    firebase_mock.create_beta_signup.assert_not_called()


def test_storage_failure_is_safe(unauthed_client, firebase_mock, caplog):
    firebase_mock.create_beta_signup.side_effect = RuntimeError('person@example.com secret')
    response = unauthed_client.post('/beta-signups', json={
        'email': 'person@example.com', 'consent': True,
    })
    assert response.status_code == 503
    assert 'person@example.com' not in response.text
    assert 'person@example.com' not in caplog.text


def test_firestore_create_is_atomic_and_duplicate_succeeds():
    manager = object.__new__(FirebaseManager)
    manager.db = MagicMock()
    doc = manager.db.collection.return_value.document.return_value
    doc.create.side_effect = [None, AlreadyExists('exists')]
    manager.create_beta_signup('person@example.com')
    manager.create_beta_signup('person@example.com')
    manager.db.collection.assert_called_with('beta_signups')
    manager.db.collection.return_value.document.assert_called_with(
        hashlib.sha256(b'person@example.com').hexdigest()
    )
    assert doc.create.call_count == 2
    assert doc.create.call_args.args[0]['email'] == 'person@example.com'
    assert doc.create.call_args.args[0]['consent'] is True


def test_signup_rate_limit_uses_ip_even_with_bearer(unauthed_client):
    from app.server import limiter
    limiter.reset()
    limiter.enabled = True
    try:
        statuses = [unauthed_client.post('/beta-signups',
            headers={'Authorization': f'Bearer token-{i}'},
            json={'email': 'person@example.com', 'consent': True}).status_code
            for i in range(6)]
        assert statuses == [200] * 5 + [429]
    finally:
        limiter.enabled = False
        limiter.reset()
