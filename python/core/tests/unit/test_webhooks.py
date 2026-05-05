"""Unit tests for webhook signing and WebhookEndpoint.subscribes_to."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from goderash_core.models.tenant import WebhookEndpoint
from goderash_core.webhooks.dispatcher import sign_payload


class TestSignPayload:
    def test_produces_sha256_prefix(self):
        sig = sign_payload(b"hello", "secret")
        assert sig.startswith("sha256=")

    def test_matches_manual_hmac(self):
        body = b'{"event_type":"chain.broken"}'
        secret = "my-test-secret"
        expected = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        assert sign_payload(body, secret) == expected

    def test_different_bodies_produce_different_signatures(self):
        secret = "s3cr3t"
        sig1 = sign_payload(b"body1", secret)
        sig2 = sign_payload(b"body2", secret)
        assert sig1 != sig2

    def test_different_secrets_produce_different_signatures(self):
        body = b"same-body"
        sig1 = sign_payload(body, "secret-a")
        sig2 = sign_payload(body, "secret-b")
        assert sig1 != sig2

    def test_empty_body_is_deterministic(self):
        sig1 = sign_payload(b"", "key")
        sig2 = sign_payload(b"", "key")
        assert sig1 == sig2


def _stub(events_filter: str):
    """Return an object whose subscribes_to method uses the given filter string."""
    return SimpleNamespace(events_filter=events_filter,
                           subscribes_to=lambda et: WebhookEndpoint.subscribes_to(
                               SimpleNamespace(events_filter=events_filter), et
                           ))


class TestWebhookEndpointSubscribesTo:
    def test_single_event_match(self):
        ep = _stub("chain.broken")
        assert WebhookEndpoint.subscribes_to(ep, "chain.broken") is True

    def test_single_event_no_match(self):
        ep = _stub("chain.broken")
        assert WebhookEndpoint.subscribes_to(ep, "quota.warning") is False

    def test_multi_event_match(self):
        ep = _stub("chain.broken,quota.warning,quota.exceeded")
        assert WebhookEndpoint.subscribes_to(ep, "quota.warning") is True

    def test_multi_event_no_match(self):
        ep = _stub("chain.broken,quota.warning")
        assert WebhookEndpoint.subscribes_to(ep, "quota.exceeded") is False

    def test_whitespace_trimmed_from_filter(self):
        ep = _stub("chain.broken, quota.warning")
        assert WebhookEndpoint.subscribes_to(ep, "quota.warning") is True

    def test_generate_secret_is_64_hex_chars(self):
        secret = WebhookEndpoint.generate_secret()
        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)

    def test_generate_secret_unique_each_call(self):
        assert WebhookEndpoint.generate_secret() != WebhookEndpoint.generate_secret()
