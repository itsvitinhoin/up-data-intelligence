"""Firebase server session cookies; access is reread for every authorization."""

import time
from datetime import timedelta
from typing import Any, Protocol

from src.dashboard.contracts import ReadError
from src.product_auth.access import Access, AccessRepository, resolve, verified_identity

SESSION_SECONDS = 43200


class Verifier(Protocol):
    def session(self, value: str) -> dict[str, Any]: ...
    def token(self, value: str) -> dict[str, Any]: ...
    def create(self, value: str) -> str: ...
    def revoke(self, uid: str) -> None: ...


class FirebaseVerifier:
    def __init__(self, app: Any):
        self.app = app

    def session(self, value: str) -> dict[str, Any]:
        from firebase_admin import auth

        try:
            return dict(auth.verify_session_cookie(value, check_revoked=True, app=self.app))
        except Exception:
            raise ReadError(401, "invalid_session") from None

    def token(self, value: str) -> dict[str, Any]:
        from firebase_admin import auth

        try:
            return dict(auth.verify_id_token(value, check_revoked=True, app=self.app))
        except Exception:
            raise ReadError(401, "invalid_identity_token") from None

    def create(self, value: str) -> str:
        from firebase_admin import auth

        try:
            return str(
                auth.create_session_cookie(
                    value, expires_in=timedelta(seconds=SESSION_SECONDS), app=self.app
                )
            )
        except Exception:
            raise ReadError(503, "session_exchange_failed") from None

    def revoke(self, uid: str) -> None:
        from firebase_admin import auth

        try:
            auth.revoke_refresh_tokens(uid, app=self.app)
        except Exception:
            # Never retry a mutation with unknown outcome automatically.
            raise ReadError(503, "session_revocation_outcome_unknown") from None


class Sessions:
    def __init__(self, verifier: Verifier, repository: AccessRepository):
        self.verifier, self.repository = verifier, repository

    def authenticate(self, cookie: str) -> Access:
        if not cookie or len(cookie) > 8192:
            raise ReadError(401, "unauthenticated")
        return resolve(verified_identity(self.verifier.session(cookie)), self.repository)

    def exchange(self, token: str) -> str:
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise ReadError(401, "invalid_identity_token")
        claims = self.verifier.token(token)
        auth_time = claims.get("auth_time")
        if type(auth_time) is not int or not 0 <= time.time() - auth_time <= 300:
            raise ReadError(401, "recent_login_required")
        resolve(verified_identity(claims), self.repository)
        return self.verifier.create(token)

    def logout(self, cookie: str) -> None:
        # Disabled access must not prevent revocation of the user's own session.
        identity = verified_identity(self.verifier.session(cookie))
        self.verifier.revoke(identity.uid)
