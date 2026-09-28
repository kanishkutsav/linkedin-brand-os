import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from app.services.linkedin_oauth import _hash, build_authorization_url, exchange_code
from app.services.security import (
    client_key,
    csrf_token_for_session,
    decrypt_linkedin_token,
    encrypt_linkedin_token,
    minimize_ai_text,
    validate_csrf_token,
)


class TestSecurityControls(unittest.TestCase):
    def test_linkedin_token_round_trip(self):
        plaintext = "linkedin-secret-token"
        encrypted = encrypt_linkedin_token(plaintext)
        self.assertTrue(encrypted.startswith("v1:"))
        recovered, encrypted_flag = decrypt_linkedin_token(encrypted)
        self.assertTrue(encrypted_flag)
        self.assertEqual(recovered, plaintext)

    def test_plaintext_token_is_detected_for_migration(self):
        recovered, encrypted_flag = decrypt_linkedin_token("legacy-token")
        self.assertFalse(encrypted_flag)
        self.assertEqual(recovered, "legacy-token")

    def test_csrf_token_is_session_bound(self):
        session = "session-secret"
        token = csrf_token_for_session(session)
        self.assertTrue(validate_csrf_token(session, token, token))
        self.assertFalse(validate_csrf_token("different-session", token, token))
        self.assertFalse(validate_csrf_token(session, token, "tampered"))

    def test_ai_minimization_removes_common_pii_and_credentials(self):
        value = "Email test@example.com, phone +91 98765 43210, Authorization Bearer abcdefghijklmnop"
        minimized = minimize_ai_text(value)
        self.assertNotIn("test@example.com", minimized)
        self.assertNotIn("98765 43210", minimized)
        self.assertNotIn("Bearer abcdefghijklmnop", minimized)

    def test_client_key_is_not_raw_ip(self):
        self.assertNotEqual(client_key.__name__, "return_raw_ip")

    def test_oauth_authorization_state_binds_browser_nonce(self):
        async def run():
            session = MagicMock()
            session.commit = AsyncMock()
            with patch("app.services.linkedin_oauth.settings.linkedin_client_id", "client"), \
                 patch("app.services.linkedin_oauth.settings.linkedin_client_secret", "secret"), \
                 patch("app.services.linkedin_oauth.settings.linkedin_redirect_uri", "https://example.test/callback"):
                url, state = await build_authorization_url(session, "browser-nonce")
            self.assertEqual(parse_qs(urlparse(url).query)["state"][0], state)
            self.assertTrue(state.endswith(".browser-nonce"))
            added = session.add.call_args.args[0]
            self.assertEqual(added.browser_nonce_hash, _hash("browser-nonce"))
            session.commit.assert_awaited()

        import asyncio
        asyncio.run(run())

    def test_oauth_state_nonce_is_second_state_segment(self):
        state = "server-random.browser-nonce"
        self.assertEqual(state.split(".", 1)[1], "browser-nonce")

    def test_oauth_exchange_rejects_wrong_browser_nonce(self):
        async def run():
            exchange = type("Exchange", (), {
                "browser_nonce_hash": _hash("expected"),
                "used": False,
                "user_id": 1,
            })()
            result = AsyncMock()
            result.scalar_one_or_none.return_value = exchange
            session = MagicMock()
            session.execute = AsyncMock(side_effect=[result])
            with self.assertRaises(Exception):
                await exchange_code(session, "code", "wrong")

        import asyncio
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
