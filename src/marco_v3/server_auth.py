"""Auth for the Marco UI server.

One user (Rudolph). The ``MARCO_UI_TOKEN`` env var is the shared secret. The
server accepts it via ``Authorization: Bearer`` header OR a signed session
cookie set by the ``/login`` form.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass


COOKIE_NAME = 'marco_session'
TOKEN_ENV = 'MARCO_UI_TOKEN'
SECRET_ENV = 'MARCO_UI_SECRET'


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthConfig:
    token: str
    secret: str


def load_auth_config() -> AuthConfig:
    token = os.environ.get(TOKEN_ENV, '').strip()
    if not token:
        raise AuthError(
            f'{TOKEN_ENV} environment variable is required to start the Marco server. '
            'Set a strong token (e.g. `openssl rand -hex 32`).'
        )
    secret = os.environ.get(SECRET_ENV, '').strip()
    if not secret:
        # Fall back to the token itself; still signed, but easier single-knob setup.
        secret = token
    return AuthConfig(token=token, secret=secret)


def verify_bearer(header_value: str | None, config: AuthConfig) -> bool:
    if not header_value:
        return False
    scheme, _, credentials = header_value.partition(' ')
    if scheme.lower() != 'bearer' or not credentials:
        return False
    return hmac.compare_digest(credentials.strip(), config.token)


def verify_cookie(cookie_value: str | None, config: AuthConfig) -> bool:
    if not cookie_value:
        return False
    try:
        from itsdangerous import BadSignature, URLSafeSerializer

        serializer = URLSafeSerializer(config.secret, salt='marco-session')
        payload = serializer.loads(cookie_value)
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(str(payload.get('token', '')), config.token)


def sign_cookie(config: AuthConfig) -> str:
    from itsdangerous import URLSafeSerializer

    serializer = URLSafeSerializer(config.secret, salt='marco-session')
    return serializer.dumps({'token': config.token})


def verify_request_token(*, bearer: str | None, cookie: str | None, config: AuthConfig) -> bool:
    return verify_bearer(bearer, config) or verify_cookie(cookie, config)


def verify_form_token(submitted: str, config: AuthConfig) -> bool:
    return hmac.compare_digest(submitted.strip(), config.token)
