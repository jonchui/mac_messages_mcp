"""
Minimal OAuth 2.1 Authorization Server for MCP remote access.

Implements the subset of OAuth 2.1 required by the MCP specification:
- Dynamic Client Registration (RFC 7591)
- Authorization Code flow with PKCE (RFC 7636)
- Bearer token validation (RFC 6750)
- Server Metadata Discovery (RFC 8414)
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mac_messages_mcp.oauth")


@dataclass
class OAuthClient:
    client_id: str
    client_secret: Optional[str] = None
    redirect_uris: list[str] = field(default_factory=list)
    client_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class AuthorizationCode:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    scope: str
    created_at: float = field(default_factory=time.time)
    expires_in: int = 600  # 10 minutes


@dataclass
class AccessToken:
    token: str
    client_id: str
    scope: str
    created_at: float = field(default_factory=time.time)
    expires_in: int = 86400  # 24 hours


class OAuthProvider:
    """In-memory OAuth 2.1 authorization server with optional file persistence."""

    def __init__(self, server_url: str, persist_path: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.persist_path = Path(persist_path) if persist_path else None

        self.clients: dict[str, OAuthClient] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.access_tokens: dict[str, AccessToken] = {}

        if self.persist_path and self.persist_path.exists():
            self._load()

    def get_server_metadata(self) -> dict:
        """RFC 8414: OAuth 2.0 Authorization Server Metadata."""
        return {
            "issuer": self.server_url,
            "authorization_endpoint": f"{self.server_url}/authorize",
            "token_endpoint": f"{self.server_url}/token",
            "registration_endpoint": f"{self.server_url}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "none",
            ],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": ["mcp"],
        }

    def get_resource_metadata(self) -> dict:
        """RFC 9728: OAuth Protected Resource Metadata."""
        return {
            "resource": self.server_url,
            "authorization_servers": [self.server_url],
            "scopes_supported": ["mcp"],
            "bearer_methods_supported": ["header"],
        }

    def register_client(self, registration_data: dict) -> dict:
        """Dynamic client registration (RFC 7591)."""
        client_id = secrets.token_urlsafe(32)
        client_secret = secrets.token_urlsafe(48)

        client = OAuthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=registration_data.get("redirect_uris", []),
            client_name=registration_data.get("client_name"),
        )
        self.clients[client_id] = client
        self._persist()

        logger.info(f"Registered new client: {client.client_name or client_id}")
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": client.client_name,
            "redirect_uris": client.redirect_uris,
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        }

    def create_authorization_code(
        self,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
        scope: str = "mcp",
    ) -> str:
        """Create an authorization code after user consent."""
        if client_id not in self.clients:
            raise ValueError("Unknown client")

        code = secrets.token_urlsafe(48)
        self.auth_codes[code] = AuthorizationCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
        )
        self._persist()
        logger.info(f"Created authorization code for client {client_id}")
        return code

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict:
        """Exchange authorization code for access token."""
        auth_code = self.auth_codes.get(code)
        if not auth_code:
            raise ValueError("Invalid authorization code")

        if time.time() - auth_code.created_at > auth_code.expires_in:
            del self.auth_codes[code]
            self._persist()
            raise ValueError("Authorization code expired")

        if auth_code.client_id != client_id:
            raise ValueError("Client ID mismatch")

        if auth_code.redirect_uri != redirect_uri:
            raise ValueError("Redirect URI mismatch")

        # Verify PKCE (S256)
        if auth_code.code_challenge_method == "S256":
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            if expected != auth_code.code_challenge:
                raise ValueError("PKCE verification failed")

        # Issue access token
        token = secrets.token_urlsafe(48)
        self.access_tokens[token] = AccessToken(
            token=token,
            client_id=client_id,
            scope=auth_code.scope,
        )

        del self.auth_codes[code]
        self._persist()

        logger.info(f"Issued access token for client {client_id}")
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "scope": auth_code.scope,
        }

    def validate_token(self, token: str) -> Optional[AccessToken]:
        """Validate a Bearer token. Returns AccessToken if valid, None otherwise."""
        access_token = self.access_tokens.get(token)
        if not access_token:
            return None

        if time.time() - access_token.created_at > access_token.expires_in:
            del self.access_tokens[token]
            self._persist()
            return None

        return access_token

    def _persist(self):
        """Save state to disk for persistence across restarts."""
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "clients": {k: asdict(v) for k, v in self.clients.items()},
            "access_tokens": {k: asdict(v) for k, v in self.access_tokens.items()},
            # Auth codes are short-lived, no need to persist
        }
        self.persist_path.write_text(json.dumps(state, indent=2))

    def _load(self):
        """Load persisted state from disk."""
        try:
            data = json.loads(self.persist_path.read_text())
            now = time.time()
            for k, v in data.get("clients", {}).items():
                self.clients[k] = OAuthClient(**v)
            for k, v in data.get("access_tokens", {}).items():
                at = AccessToken(**v)
                # Skip expired tokens
                if now - at.created_at < at.expires_in:
                    self.access_tokens[k] = at
            logger.info(
                f"Loaded {len(self.clients)} clients, "
                f"{len(self.access_tokens)} active tokens from disk"
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Could not load persisted state: {e}. Starting fresh.")
