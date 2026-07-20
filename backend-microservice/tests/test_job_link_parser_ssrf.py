"""
Regression tests for SSRF-guard gaps in job_link_parser._is_safe_url.

Business rule: /dream-job/from-link lets an authenticated user hand the
backend an arbitrary URL to fetch. The guard must reject every address that
resolves to a non-public target — including two classes that were previously
missed: 0.0.0.0/:: (unspecified) and IPv4-mapped IPv6 wrapping a private IP
(e.g. ::ffff:169.254.169.254 wrapping the cloud metadata endpoint).
"""

from unittest.mock import patch

from app.services.job_link_parser import _is_safe_url


def _fake_addrinfo(ip: str):
    return [(None, None, None, None, (ip, 0))]


class TestIsSafeUrlGaps:
    def test_rejects_unspecified_ipv4(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("0.0.0.0")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False

    def test_rejects_unspecified_ipv6(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("::")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False

    def test_rejects_ipv4_mapped_link_local_metadata_endpoint(self):
        """::ffff:169.254.169.254 wraps the cloud metadata IP in an IPv6
        literal — must be unwrapped and rejected, not treated as a bare
        (non-private-looking) IPv6 address."""
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("::ffff:169.254.169.254")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False

    def test_rejects_ipv4_mapped_private_ip(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("::ffff:10.0.0.5")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False

    def test_allows_public_ip(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("8.8.8.8")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is True

    def test_still_rejects_loopback(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("127.0.0.1")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False

    def test_still_rejects_metadata_endpoint(self):
        with patch("socket.getaddrinfo", return_value=_fake_addrinfo("169.254.169.254")):
            ok, reason = _is_safe_url("http://example.com/job")
        assert ok is False
