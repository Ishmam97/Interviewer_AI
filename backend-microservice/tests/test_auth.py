"""
Tests for /auth/* endpoints.

All Firebase calls are mocked via the session-scoped fixtures in conftest.py.
"""

import pytest


class TestSignUp:
    def test_signup_success(self, client):
        r = client.post("/auth/signup", json={
            "email": "new@example.com",
            "password": "strongpass123",
            "full_name": "New User",
        })
        assert r.status_code == 200
        body = r.json()
        assert "user" in body
        assert "session" in body
        assert body["session"]["access_token"] == "id-token-abc"

    def test_signup_duplicate_raises_409(self, client, firebase_mock):
        firebase_mock.sign_up.return_value = {
            "success": False,
            "error": "Email already registered",
        }
        r = client.post("/auth/signup", json={
            "email": "dup@example.com",
            "password": "strongpass123",
        })
        assert r.status_code == 409
        # restore default
        firebase_mock.sign_up.return_value = {
            "success": True,
            "user": {"uid": "test-uid-123", "email": "test@example.com"},
            "custom_token": "custom-token",
        }

    def test_signup_weak_password_raises_400(self, client, firebase_mock):
        firebase_mock.sign_up.return_value = {
            "success": False,
            "error": "Password should contain at least 8 characters",
        }
        r = client.post("/auth/signup", json={
            "email": "weak@example.com",
            "password": "abc",
        })
        assert r.status_code == 400
        # restore
        firebase_mock.sign_up.return_value = {
            "success": True,
            "user": {"uid": "test-uid-123", "email": "test@example.com"},
            "custom_token": "custom-token",
        }

    def test_signup_missing_email_raises_422(self, client):
        r = client.post("/auth/signup", json={"password": "strongpass123"})
        assert r.status_code == 422


class TestSignIn:
    def test_signin_success(self, client):
        r = client.post("/auth/signin", json={
            "email": "test@example.com",
            "password": "strongpass123",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["session"]["access_token"] == "id-token-abc"

    def test_signin_wrong_credentials_raises_401(self, client, firebase_mock):
        firebase_mock.sign_in.return_value = {
            "success": False,
            "error": "Invalid credentials",
        }
        r = client.post("/auth/signin", json={
            "email": "test@example.com",
            "password": "wrongpass",
        })
        assert r.status_code == 401
        # restore
        firebase_mock.sign_in.return_value = {
            "success": True,
            "user": {"uid": "test-uid-123", "email": "test@example.com"},
            "session": {"access_token": "id-token-abc"},
        }


class TestGetMe:
    def test_me_authenticated(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["id"] == "test-uid-123"
        assert body["user"]["email"] == "test@example.com"

    def test_me_unauthenticated(self, unauthed_client, firebase_mock):
        # verify_id_token returns None → server raises 401
        firebase_mock.verify_id_token.return_value = None
        r = unauthed_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert r.status_code == 401

    def test_me_no_token(self, unauthed_client):
        # No Authorization header at all → HTTPBearer returns None → 401
        r = unauthed_client.get("/auth/me")
        assert r.status_code == 401


class TestSignOut:
    def test_signout(self, client):
        r = client.post("/auth/signout")
        assert r.status_code == 200
        assert "message" in r.json()
