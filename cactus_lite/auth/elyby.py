"""Ely.by authentication (Yggdrasil-compatible API).

Docs: https://docs.ely.by/en/minecraft-auth.html
Only the launcher-side flow is implemented: authenticate / refresh / validate /
invalidate. The game itself talks to Ely.by through authlib-injector.
"""

import uuid

from cactus_lite.core.net import post_json

BASE = "https://authserver.ely.by"
TWO_FACTOR_MARKER = "two factor"


class AuthError(RuntimeError):
    """Authentication failed for a reason worth showing to the user."""


class TwoFactorRequired(AuthError):
    def __init__(self):
        super().__init__("Аккаунт защищён двухфакторной аутентификацией.")


def new_client_token():
    return uuid.uuid4().hex


def _error_message(body):
    message = (body or {}).get("errorMessage") or (body or {}).get("error") or ""
    return message or "Сервер Ely.by вернул ошибку."


def _check(status, body):
    if status == 200:
        return body
    message = _error_message(body)
    if TWO_FACTOR_MARKER in message.lower():
        raise TwoFactorRequired()
    raise AuthError(message)


def authenticate(login, password, totp=None, client_token=None):
    """Log in with a username/e-mail and password.

    Ely.by has no field for a TOTP token, so it is appended to the password as
    `password:token` (see the docs). Returns a profile dict.
    """
    if not login or not password:
        raise AuthError("Введите логин и пароль.")
    client_token = client_token or new_client_token()
    secret = f"{password}:{totp.strip()}" if totp and totp.strip() else password
    status, body = post_json(f"{BASE}/auth/authenticate", {
        "username": login,
        "password": secret,
        "clientToken": client_token,
        "requestUser": True,
    })
    data = _check(status, body)
    profile = data.get("selectedProfile") or {}
    if not data.get("accessToken") or not profile.get("id"):
        raise AuthError("Ely.by не вернул профиль игрока.")
    return {
        "kind": "elyby",
        "username": profile.get("name") or login,
        "uuid": profile["id"],
        "access_token": data["accessToken"],
        "client_token": data.get("clientToken") or client_token,
    }


def refresh(account):
    """Exchange a stored access token for a fresh one."""
    status, body = post_json(f"{BASE}/auth/refresh", {
        "accessToken": account.get("access_token", ""),
        "clientToken": account.get("client_token", ""),
        "requestUser": True,
    })
    data = _check(status, body)
    profile = data.get("selectedProfile") or {}
    updated = dict(account)
    updated["access_token"] = data.get("accessToken") or account.get("access_token")
    updated["client_token"] = data.get("clientToken") or account.get("client_token")
    if profile.get("name"):
        updated["username"] = profile["name"]
    if profile.get("id"):
        updated["uuid"] = profile["id"]
    return updated


def is_valid(account):
    status, _body = post_json(f"{BASE}/auth/validate",
                             {"accessToken": account.get("access_token", "")})
    return status == 200


def invalidate(account):
    post_json(f"{BASE}/auth/invalidate", {
        "accessToken": account.get("access_token", ""),
        "clientToken": account.get("client_token", ""),
    })


def ensure_session(account):
    """Return an account with a valid access token, refreshing if necessary."""
    if is_valid(account):
        return account
    return refresh(account)
