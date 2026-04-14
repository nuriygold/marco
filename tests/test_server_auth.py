from __future__ import annotations

import unittest
from unittest import mock

from src.marco_v3.server_auth import (
    AuthConfig,
    AuthError,
    load_auth_config,
    sign_cookie,
    verify_bearer,
    verify_cookie,
    verify_form_token,
    verify_request_token,
)


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = AuthConfig(token='test-token', secret='test-secret')

    def test_load_auth_config_requires_token(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(AuthError):
                load_auth_config()

    def test_load_auth_config_falls_back_secret_to_token(self) -> None:
        with mock.patch.dict('os.environ', {'MARCO_UI_TOKEN': 'abc'}, clear=True):
            cfg = load_auth_config()
            self.assertEqual(cfg.token, 'abc')
            self.assertEqual(cfg.secret, 'abc')

    def test_verify_bearer(self) -> None:
        self.assertTrue(verify_bearer('Bearer test-token', self.cfg))
        self.assertTrue(verify_bearer('bearer test-token', self.cfg))
        self.assertFalse(verify_bearer('Bearer wrong', self.cfg))
        self.assertFalse(verify_bearer('Basic test-token', self.cfg))
        self.assertFalse(verify_bearer(None, self.cfg))
        self.assertFalse(verify_bearer('', self.cfg))

    def test_form_token(self) -> None:
        self.assertTrue(verify_form_token('test-token', self.cfg))
        self.assertTrue(verify_form_token('  test-token  ', self.cfg))
        self.assertFalse(verify_form_token('nope', self.cfg))

    def test_signed_cookie_roundtrip(self) -> None:
        signed = sign_cookie(self.cfg)
        self.assertTrue(verify_cookie(signed, self.cfg))
        self.assertFalse(verify_cookie('garbage', self.cfg))
        self.assertFalse(verify_cookie(None, self.cfg))

    def test_verify_request_token_accepts_either(self) -> None:
        signed = sign_cookie(self.cfg)
        self.assertTrue(verify_request_token(bearer='Bearer test-token', cookie=None, config=self.cfg))
        self.assertTrue(verify_request_token(bearer=None, cookie=signed, config=self.cfg))
        self.assertFalse(verify_request_token(bearer='Bearer x', cookie='y', config=self.cfg))


if __name__ == '__main__':
    unittest.main()
