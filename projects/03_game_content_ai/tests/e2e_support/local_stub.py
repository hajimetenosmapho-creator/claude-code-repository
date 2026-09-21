"""
T2: Local Stub HTTPサーバー（WordPress / Anthropic / RSS 3系統対応）。

docs/design/mvp_end_to_end_hardening_validation.md 7.5.5節の要件を実装する
test-only helper。production source（src/・scripts/・main.py）には一切
依存を追加しない——main.py実subprocessは`WP_SITE_URL`・`ANTHROPIC_BASE_URL`・
`NEWS_RSS_FEED_URLS_OVERRIDE`環境変数経由でこのスタブへ向けられる（既存の
環境変数機構のみを使う、7.5.1節）。

- `127.0.0.1`の動的ポートへ明示bind、`serve_forever()`開始後にのみ
  readinessを公開する（7.5.5節冒頭要件）。
- WordPress：`/wp-json/wp/v2/posts`への正確なpath/認証ヘッダ/draft payloadを
  記録し、`WordPressOutput`が消費するJSONフィールド
  （id/slug/status/title/link）を返す。
- RSS：`NEWS_RSS_FEED_URLS_OVERRIDE`が指す16個の個別パスそれぞれに、
  固定fixtureまたはリクエスト回数に応じた決定的なレスポンス系列を返す
  （10.2節のcanonical/retry 2段階fixtureに対応）。
- Anthropic：`client.messages.create()`の非streamingレスポンス形状
  （id/type/role/model/content/stop_reason/usage）を満たすJSONを返す。
"""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlsplit

WORDPRESS_REQUIRED_PAYLOAD_KEYS = ("title", "content", "status", "excerpt", "slug")

WORDPRESS_POST_PATH = "/wp-json/wp/v2/posts"
ANTHROPIC_MESSAGES_PATH_SUFFIX = "/v1/messages"


def build_rss_xml(items: list[dict]) -> bytes:
    """RSS 2.0 XML（channel + 0件以上のitem）をbytesで組み立てる。"""
    item_xml_parts = []
    for item in items:
        item_xml_parts.append(
            "<item>"
            f"<title>{_escape(item['title'])}</title>"
            f"<link>{_escape(item['link'])}</link>"
            f"<description>{_escape(item.get('description', ''))}</description>"
            f"<pubDate>{_escape(item.get('pub_date', 'Mon, 01 Jan 2024 00:00:00 GMT'))}</pubDate>"
            "</item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>Local Stub Feed</title>"
        "<link>http://127.0.0.1/</link>"
        "<description>test-only fixture</description>"
        + "".join(item_xml_parts)
        + "</channel></rss>"
    )
    return body.encode("utf-8")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


EMPTY_RSS_XML = build_rss_xml([])


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict
    body: bytes


@dataclass
class _RssPathState:
    sequence: list = field(default_factory=list)
    request_count: int = 0

    def next_response(self) -> bytes:
        self.request_count += 1
        if not self.sequence:
            return EMPTY_RSS_XML
        index = min(self.request_count - 1, len(self.sequence) - 1)
        return self.sequence[index]


class _Handler(BaseHTTPRequestHandler):
    server: "_StubHTTPServer"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # テスト出力を静かに保つ（stdoutを汚さない）

    def do_GET(self):
        path = urlsplit(self.path).path
        stub: LocalStub = self.server.stub
        # 【Post-Codex Full Independent Review Amendment、Suggestion対応】
        # next_response()（内部counterの読み取り・更新）もlockの内側で行う。
        # 従来はlockの外側で呼んでいたため、ThreadingHTTPServerが同一RSS
        # pathへ並行リクエストを受けた場合、counterのincrementに競合が
        # 生じ、レスポンスの決定性が損なわれうる可能性があった。
        with stub._lock:
            stub._requests.append(
                RecordedRequest("GET", path, dict(self.headers), b"")
            )
            state = stub._rss_paths.get(path)
            body = state.next_response() if state is not None else None
        if body is not None:
            self._respond(200, body, content_type="application/rss+xml")
            return
        self._respond(404, b"not found")

    def do_POST(self):
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        stub: LocalStub = self.server.stub
        with stub._lock:
            stub._requests.append(
                RecordedRequest("POST", path, dict(self.headers), body)
            )

        if path == WORDPRESS_POST_PATH:
            status, response_body = stub._handle_wordpress_post(dict(self.headers), body)
            self._respond(status, response_body, content_type="application/json")
            return

        if path.endswith(ANTHROPIC_MESSAGES_PATH_SUFFIX):
            status, response_body = stub._handle_anthropic_post(body)
            self._respond(status, response_body, content_type="application/json")
            return

        self._respond(404, b"not found")

    def _respond(self, status: int, body: bytes, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StubHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    stub: "LocalStub"


def _default_anthropic_responder(request_json: dict) -> str:
    """importance判定プロンプトを検出したらimportance JSONを、それ以外は
    記事本文/SEOタイトル/X投稿文として使える単純な非空テキストを返す。"""
    messages = request_json.get("messages", [])
    prompt_text = " ".join(
        str(m.get("content", "")) for m in messages if isinstance(m, dict)
    )
    if "importance" in prompt_text.lower() or "重要度" in prompt_text:
        return json.dumps({"importance": "A", "reason": "stub fixed response"}, ensure_ascii=False)
    return "スタブ生成テキスト（Local Stub固定応答）"


class LocalStub:
    """WordPress / Anthropic / RSSの3系統をまとめて提供するtest-only stub。

    使用例::

        stub = LocalStub(rss_source_names=list(RSS_FEEDS.keys()))
        stub.start()
        try:
            ...
        finally:
            stub.stop()
    """

    def __init__(self, rss_source_names: list[str]):
        self._rss_source_names = list(rss_source_names)
        self._rss_slug_by_source = {
            name: f"/rss/{i:02d}" for i, name in enumerate(self._rss_source_names)
        }
        self._lock = threading.Lock()
        self._rss_paths: dict[str, _RssPathState] = {
            path: _RssPathState() for path in self._rss_slug_by_source.values()
        }
        self._requests: list[RecordedRequest] = []
        self._wordpress_rejections: list[str] = []
        self._wordpress_status = 201
        self._wordpress_response_body: dict = {
            "id": 1001,
            "slug": "stub-post",
            "status": "draft",
            "title": {"rendered": "stub"},
            "link": "http://127.0.0.1/?p=1001",
        }
        self._wordpress_expected_auth: Optional[tuple[str, str]] = None
        self._wordpress_expected_status: str = "draft"
        self._anthropic_responder: Callable[[dict], str] = _default_anthropic_responder
        self._server: Optional[_StubHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ── lifecycle ──────────────────────────────────────────────
    def start(self) -> "LocalStub":
        server = _StubHTTPServer(("127.0.0.1", 0), _Handler)
        server.stub = self
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            finally:
                self._server.server_close()
                self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "LocalStub":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ── addressing ─────────────────────────────────────────────
    @property
    def port(self) -> int:
        assert self._server is not None, "LocalStub is not started"
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def rss_url_for(self, source_name: str) -> str:
        return self.base_url + self._rss_slug_by_source[source_name]

    def rss_override_json(self) -> str:
        """NEWS_RSS_FEED_URLS_OVERRIDE用のJSON文字列（16キー完全一致）を返す。"""
        return json.dumps(
            {name: self.rss_url_for(name) for name in self._rss_source_names},
            ensure_ascii=False,
        )

    # ── RSS fixture configuration ──────────────────────────────
    def set_rss_fixed_items(self, source_name: str, items: list[dict]) -> None:
        """指定sourceの全リクエストへ同一のitemsを返す（Scenario A/B向け）。"""
        path = self._rss_slug_by_source[source_name]
        xml = build_rss_xml(items)
        with self._lock:
            self._rss_paths[path] = _RssPathState(sequence=[xml])
            self._rss_paths[path].sequence = [xml]

    def set_rss_sequence(self, source_name: str, item_lists: list[list[dict]]) -> None:
        """指定sourceについて、1回目/2回目/…のリクエストへ順に異なるitemsを
        返す（Scenario Cのcanonical/retry 2段階fixture向け）。最後の要素が
        以降のリクエストへも繰り返し使われる。"""
        path = self._rss_slug_by_source[source_name]
        sequence = [build_rss_xml(items) for items in item_lists]
        with self._lock:
            self._rss_paths[path] = _RssPathState(sequence=sequence)

    def rss_request_count(self, source_name: str) -> int:
        path = self._rss_slug_by_source[source_name]
        with self._lock:
            return self._rss_paths[path].request_count

    # ── WordPress fixture configuration ────────────────────────
    def set_wordpress_response(self, status: int, body: dict) -> None:
        self._wordpress_status = status
        self._wordpress_response_body = body

    def set_wordpress_expected_auth(self, username: str, password: str) -> None:
        """POST受理前に検証するBasic認証の期待値を設定する（Post-Codex-delta-
        review Amendment、7.5.5節）。未設定の場合、認証ヘッダの検証は行わない
        （fail-openにはしない——各シナリオが必ず明示的に呼び出す契約とする）。"""
        self._wordpress_expected_auth = (username, password)

    def set_wordpress_expected_status(self, status_value: str) -> None:
        self._wordpress_expected_status = status_value

    def _validate_wordpress_request(self, headers: dict, body: bytes) -> Optional[str]:
        """認証・必須payload・status固定値を検証する。問題なければNone、
        問題があれば拒否理由の文字列を返す（POST成功前のfail-closed検証、
        7.5.5節）。

        【Post-Codex Full Independent Review Amendment、Minor#1対応】
        `set_wordpress_expected_auth()`が一度も呼ばれていない（期待認証情報が
        未設定の）場合、従来は認証検証自体をskipしてしまい、fail-open
        （未設定＝無条件許可）になっていた。これを、未設定であること自体を
        拒否理由とするfail-closedへ変更する——WordPress成功経路を使う全ての
        シナリオは、`set_wordpress_expected_auth()`を明示的に呼ぶ契約と
        なる（既存シナリオA・B・C・D・F2は全て呼び出し済み、7.5.5節）。"""
        if self._wordpress_expected_auth is None:
            return "WordPress expected auth not configured (fail-closed default)"

        expected_username, expected_password = self._wordpress_expected_auth
        expected_token = base64.b64encode(
            f"{expected_username}:{expected_password}".encode("utf-8")
        ).decode("ascii")
        auth_header = headers.get("Authorization", "")
        if auth_header != f"Basic {expected_token}":
            return "unexpected or missing Basic Authorization header"

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "request body is not valid JSON"

        if not isinstance(payload, dict):
            return "request body is not a JSON object"

        for key in WORDPRESS_REQUIRED_PAYLOAD_KEYS:
            if key not in payload:
                return f"required payload key missing: {key}"
            if key != "excerpt" and not payload.get(key):
                return f"required payload key is empty: {key}"

        if payload.get("status") != self._wordpress_expected_status:
            return (
                f"unexpected status value: {payload.get('status')!r} "
                f"(expected {self._wordpress_expected_status!r})"
            )

        return None

    def _handle_wordpress_post(self, headers: dict, body: bytes) -> tuple[int, bytes]:
        rejection_reason = self._validate_wordpress_request(headers, body)
        if rejection_reason is not None:
            with self._lock:
                self._wordpress_rejections.append(rejection_reason)
            error_body = json.dumps({"error": rejection_reason}, ensure_ascii=False).encode("utf-8")
            status = 401 if "Authorization" in rejection_reason else 400
            return status, error_body

        response = json.dumps(self._wordpress_response_body, ensure_ascii=False).encode("utf-8")
        return self._wordpress_status, response

    def wordpress_requests(self) -> list[RecordedRequest]:
        with self._lock:
            return [r for r in self._requests if r.path == WORDPRESS_POST_PATH]

    def wordpress_rejections(self) -> list[str]:
        with self._lock:
            return list(self._wordpress_rejections)

    # ── Anthropic fixture configuration ────────────────────────
    def set_anthropic_responder(self, responder: Callable[[dict], str]) -> None:
        self._anthropic_responder = responder

    def _handle_anthropic_post(self, body: bytes) -> tuple[int, bytes]:
        try:
            request_json = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_json = {}
        text = self._anthropic_responder(request_json)
        response = {
            "id": "msg_stub_0001",
            "type": "message",
            "role": "assistant",
            "model": request_json.get("model", "stub-model"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        return 200, json.dumps(response, ensure_ascii=False).encode("utf-8")

    def anthropic_request_count(self) -> int:
        with self._lock:
            return sum(
                1 for r in self._requests if r.path.endswith(ANTHROPIC_MESSAGES_PATH_SUFFIX)
            )

    # ── generic request log ────────────────────────────────────
    def all_requests(self) -> list[RecordedRequest]:
        with self._lock:
            return list(self._requests)
