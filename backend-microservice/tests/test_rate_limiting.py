"""
Regression test: authentication endpoints must be rate-limited per IP.

Business rule: /auth/signup and /auth/signin have no prior authentication,
making them the primary brute-force / signup-abuse surface. Rate limiting is
disabled under the test harness (ENVIRONMENT=test) so the rest of the suite
isn't flaky against real limits — this test explicitly re-enables it for the
duration of the assertion.
"""

def test_signin_rate_limited_after_threshold(client, firebase_mock):
    from app.server import limiter

    firebase_mock.sign_in.return_value = {"success": False, "error": "bad creds"}

    limiter.enabled = True
    try:
        codes = [
            client.post("/auth/signin", json={"email": "a@b.com", "password": "x"}).status_code
            for _ in range(12)
        ]
    finally:
        limiter.enabled = False

    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]
