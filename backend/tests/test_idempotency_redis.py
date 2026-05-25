"""
Idempotency + ephemeral replay: in-memory fallback and Redis-backed behavior.

Verifies X-Request-ID guard (SET NX semantics) and JSON replay cache for multi-worker setups.
"""

import unittest
from unittest.mock import MagicMock, patch

import fakeredis

from app.core import ephemeral_result_cache as erc
from app.core import idempotency as idem
from app.core.redis_store import get_redis_client, reset_redis_client_for_tests


class TestIdempotencyInMemory(unittest.TestCase):
    """No REDIS_URL: process-local dict, same semantics as before Redis."""

    def tearDown(self):
        reset_redis_client_for_tests()

    def test_second_identical_request_is_duplicate(self):
        with patch("app.core.idempotency.get_redis_client", return_value=None):
            self.assertFalse(
                idem.is_duplicate_request(
                    request_id="req-abc",
                    scope="applications.apply",
                    key="user@x.com:9",
                    ttl_seconds=90,
                )
            )
            self.assertTrue(
                idem.is_duplicate_request(
                    request_id="req-abc",
                    scope="applications.apply",
                    key="user@x.com:9",
                    ttl_seconds=90,
                )
            )


class TestIdempotencyRedis(unittest.TestCase):
    def tearDown(self):
        reset_redis_client_for_tests()

    def test_redis_set_nx_duplicate_across_workers(self):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        with patch("app.core.idempotency.get_redis_client", return_value=fake):
            self.assertFalse(
                idem.is_duplicate_request(
                    request_id="shared-rid",
                    scope="interviews.end",
                    key="42",
                    ttl_seconds=120,
                )
            )
            self.assertTrue(
                idem.is_duplicate_request(
                    request_id="shared-rid",
                    scope="interviews.end",
                    key="42",
                    ttl_seconds=120,
                )
            )
        stored = fake.get("idem:interviews.end:42:shared-rid")
        self.assertEqual(stored, "1")


class TestIdempotencyTtlFromSettings(unittest.TestCase):
    def tearDown(self):
        reset_redis_client_for_tests()

    def test_clamp_respects_settings_bounds(self):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        settings = MagicMock()
        settings.idempotency_ttl_min_seconds = 30
        settings.idempotency_ttl_max_seconds = 40
        with patch("app.core.idempotency.get_redis_client", return_value=fake), patch(
            "app.core.idempotency.get_settings", return_value=settings
        ):
            idem.is_duplicate_request(
                request_id="ttl-a",
                scope="x",
                key="k",
                ttl_seconds=200,
            )
        ttl = fake.ttl("idem:x:k:ttl-a")
        self.assertGreaterEqual(ttl, 30)
        self.assertLessEqual(ttl, 40)


class TestRedisPingReconnect(unittest.TestCase):
    def tearDown(self):
        reset_redis_client_for_tests()

    def test_ping_failure_triggers_new_connection(self):
        """Simulate dead client: ping raises on reuse, store should build a fresh FakeStrictRedis."""
        first = MagicMock()
        first.ping.side_effect = [None, ConnectionError("boom")]
        first.close = MagicMock()
        second = fakeredis.FakeStrictRedis(decode_responses=True)
        with patch("app.core.redis_store.get_settings") as gs, patch(
            "redis.Redis.from_url", side_effect=[first, second]
        ) as from_url:
            gs.return_value = MagicMock(redis_url="redis://fake")
            reset_redis_client_for_tests()
            c1 = get_redis_client()
            self.assertIs(c1, first)
            c2 = get_redis_client()
            self.assertIs(c2, second)
            self.assertEqual(from_url.call_count, 2)


class TestEphemeralReplayCache(unittest.TestCase):
    def tearDown(self):
        reset_redis_client_for_tests()

    def test_redis_replays_serialized_json(self):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        key = "idem:interviews.transcribe:7:rid-xyz"
        payload = {"text": "hello"}
        with patch("app.core.ephemeral_result_cache.get_redis_client", return_value=fake):
            self.assertIsNone(erc.cache_get(key))
            erc.cache_set(key, payload, ttl_seconds=90)
            self.assertEqual(erc.cache_get(key), payload)


if __name__ == "__main__":
    unittest.main()
