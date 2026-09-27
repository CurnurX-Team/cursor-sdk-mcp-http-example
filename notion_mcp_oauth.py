"""Notion MCP용 OAuth 2.0 Authorization Code + PKCE 클라이언트.

최초 실행에서는 브라우저 승인을 받고, 이후에는 저장한 refresh token으로
access token을 갱신한다. 토큰은 출력하지 않으며 저장 파일은 Git에서 제외한다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

MCP_URL = "https://mcp.notion.com/mcp"
PROTECTED_RESOURCE_METADATA_URL = (
    "https://mcp.notion.com/.well-known/oauth-protected-resource/mcp"
)
REDIRECT_URI = "http://localhost:8787/callback"
TOKEN_FILE = Path(__file__).resolve().parent / ".notion-mcp-oauth.json"


class NotionMcpOAuthError(RuntimeError):
    """Notion MCP OAuth를 완료할 수 없을 때 발생한다."""


def _get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Cursor-SDK-MCP-OAuth-Example/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        raise NotionMcpOAuthError(f"OAuth metadata 조회 실패: {url}") from error


def _post(url: str, data: dict[str, Any], *, form: bool = False) -> dict[str, Any]:
    if form:
        body = urllib.parse.urlencode(data).encode()
        content_type = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(data).encode()
        content_type = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            # urllib의 기본 User-Agent는 일부 OAuth/WAF 정책에서 차단될 수 있다.
            "User-Agent": "Cursor-SDK-MCP-OAuth-Example/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # 응답 본문이나 요청 데이터에는 인증 정보가 포함될 수 있어 출력하지 않는다.
        raise NotionMcpOAuthError(
            f"OAuth 요청 실패: {error.code} {error.reason} ({url})"
        ) from error
    except urllib.error.URLError as error:
        raise NotionMcpOAuthError(f"OAuth 서버 연결 실패: {url}") from error


def _discover() -> dict[str, Any]:
    """RFC 9728과 RFC 8414 metadata에서 OAuth endpoint를 찾는다."""

    protected_resource = _get(PROTECTED_RESOURCE_METADATA_URL)
    authorization_servers = protected_resource.get("authorization_servers", [])
    if not authorization_servers:
        raise NotionMcpOAuthError("Notion MCP가 authorization server를 알리지 않았습니다.")

    issuer = str(authorization_servers[0]).rstrip("/")
    authorization_server = _get(
        f"{issuer}/.well-known/oauth-authorization-server"
    )
    required = ("authorization_endpoint", "token_endpoint", "registration_endpoint")
    missing = [name for name in required if not authorization_server.get(name)]
    if missing:
        raise NotionMcpOAuthError(
            f"OAuth metadata에 필수 endpoint가 없습니다: {', '.join(missing)}"
        )
    if "S256" not in authorization_server.get(
        "code_challenge_methods_supported", []
    ):
        raise NotionMcpOAuthError("Notion MCP OAuth가 PKCE S256을 지원하지 않습니다.")

    scopes = protected_resource.get("scopes_supported") or ["default"]
    return {
        **authorization_server,
        "scope": str(scopes[0]),
    }


def _load_credentials() -> dict[str, Any]:
    if not TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise NotionMcpOAuthError(
            f"OAuth 저장 파일을 읽을 수 없습니다: {TOKEN_FILE}"
        ) from error


def _save_credentials(credentials: dict[str, Any]) -> None:
    temporary = TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(credentials, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(TOKEN_FILE)


def _register_client(metadata: dict[str, Any]) -> dict[str, Any]:
    print("1. Notion MCP에 이 예제를 OAuth 클라이언트로 등록합니다.")
    registration = _post(
        str(metadata["registration_endpoint"]),
        {
            "client_name": "Cursor SDK Python Example",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    client_id = registration.get("client_id")
    if not client_id:
        raise NotionMcpOAuthError("Notion이 OAuth client_id를 반환하지 않았습니다.")

    credentials = {
        "client_id": client_id,
        "client_secret": registration.get("client_secret"),
    }
    _save_credentials(credentials)
    return credentials


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _wait_for_authorization_code(expected_state: str) -> str:
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != "/callback":
                self.send_error(404)
                return

            if query.get("state", [""])[0] != expected_state:
                result["error"] = "OAuth state가 일치하지 않습니다."
            elif "error" in query:
                result["error"] = f"Notion 승인이 거부되었습니다: {query['error'][0]}"
            else:
                result["code"] = query.get("code", [""])[0]

            succeeded = bool(result.get("code"))
            message = (
                "Notion 인증이 완료되었습니다. 이 창을 닫아도 됩니다."
                if succeeded
                else "Notion 인증에 실패했습니다. 터미널을 확인해 주세요."
            )
            body = message.encode("utf-8")
            self.send_response(200 if succeeded else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        with HTTPServer(("localhost", 8787), CallbackHandler) as server:
            server.timeout = 300
            server.handle_request()
    except OSError as error:
        raise NotionMcpOAuthError(
            "localhost:8787을 열 수 없습니다. 다른 OAuth 로그인이나 프로그램이 "
            "이 포트를 사용 중인지 확인해 주세요."
        ) from error

    if result.get("error"):
        raise NotionMcpOAuthError(result["error"])
    if not result.get("code"):
        raise NotionMcpOAuthError("5분 안에 Notion OAuth callback을 받지 못했습니다.")
    return result["code"]


def _authorize(
    credentials: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": credentials["client_id"],
            "redirect_uri": REDIRECT_URI,
            "scope": metadata["scope"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": MCP_URL,
            "prompt": "consent",
        }
    )
    authorization_url = f"{metadata['authorization_endpoint']}?{query}"

    print("2. 브라우저에서 Notion 워크스페이스 접근을 승인해 주세요.")
    if not webbrowser.open(authorization_url):
        print(f"브라우저가 열리지 않으면 다음 URL을 직접 여세요:\n{authorization_url}")

    code = _wait_for_authorization_code(state)
    token_request = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": credentials["client_id"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "resource": MCP_URL,
    }
    if credentials.get("client_secret"):
        token_request["client_secret"] = credentials["client_secret"]

    tokens = _post(str(metadata["token_endpoint"]), token_request, form=True)
    return _merge_tokens(credentials, tokens, str(metadata["scope"]))


def _merge_tokens(
    credentials: dict[str, Any], tokens: dict[str, Any], scope: str
) -> dict[str, Any]:
    access_token = tokens.get("access_token")
    if not access_token:
        raise NotionMcpOAuthError("Notion이 OAuth access token을 반환하지 않았습니다.")

    merged = {
        **credentials,
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token")
        or credentials.get("refresh_token"),
        "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
        "scope": tokens.get("scope", scope),
    }
    _save_credentials(merged)
    return merged


def _refresh(
    credentials: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    print("1. 저장된 refresh token으로 Notion 로그인을 갱신합니다.")
    token_request = {
        "grant_type": "refresh_token",
        "refresh_token": credentials["refresh_token"],
        "client_id": credentials["client_id"],
        "scope": metadata["scope"],
        "resource": MCP_URL,
    }
    if credentials.get("client_secret"):
        token_request["client_secret"] = credentials["client_secret"]
    tokens = _post(str(metadata["token_endpoint"]), token_request, form=True)
    return _merge_tokens(credentials, tokens, str(metadata["scope"]))


def get_notion_mcp_access_token() -> str:
    """유효한 Notion MCP OAuth access token을 반환한다.

    최초 호출은 사용자 승인이 필요하다. 이후 호출은 access token이 유효하면
    그대로 사용하고, 만료가 가까우면 refresh token으로 자동 갱신한다.
    """

    metadata = _discover()
    credentials = _load_credentials()
    if not credentials.get("client_id"):
        credentials = _register_client(metadata)

    expires_at = float(credentials.get("expires_at", 0))
    if credentials.get("access_token") and expires_at > time.time() + 60:
        print("1. 저장된 Notion OAuth 로그인을 사용합니다.")
        return str(credentials["access_token"])

    if credentials.get("refresh_token"):
        credentials = _refresh(credentials, metadata)
    else:
        credentials = _authorize(credentials, metadata)

    print("3. Notion OAuth 인증이 준비되었습니다.")
    return str(credentials["access_token"])
