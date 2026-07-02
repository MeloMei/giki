"""Tests for ``giki serve`` command — HTTP handler and graph/search APIs."""

from __future__ import annotations

import json
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from giki.commands.serve import GikiHandler, HTML_FRONTEND, serve_command
from giki.wiki.parser import WikiPage, WikiLink

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PAGE = WikiPage(
    title="Hello World",
    aliases=["hw"],
    tags=["test", "demo"],
    created="2024-01-01T00:00:00+00:00",
    updated="2024-01-01T00:00:00+00:00",
    sources=[],
    body="Some body text with [[other-page]] link.",
    links=[WikiLink(target="other-page", display=None, link_type=None)],
)


def _make_store(pages: dict[str, WikiPage]):
    """Build a mock WikiStore backed by the given slug -> WikiPage mapping."""
    store = MagicMock()
    store.list_pages.return_value = list(pages.keys())
    store.all_pages.return_value = list(pages.items())

    def _exists(slug):
        return slug in pages

    def _read(slug):
        if slug not in pages:
            from giki.wiki.store import WikiStoreError

            raise WikiStoreError(f"page not found: {slug}")
        p = pages[slug]
        # Reconstruct a minimal raw page string that parse_page can handle
        return (
            "---\n"
            f"title: {p.title}\n"
            f"aliases: {p.aliases}\n"
            f"tags: {p.tags}\n"
            f"created: {p.created}\n"
            f"updated: {p.updated}\n"
            "sources: []\n"
            "---\n"
            f"{p.body}"
        )

    store.exists.side_effect = _exists
    store.read.side_effect = _read
    return store


def _make_index(results: list[tuple[str, float]]):
    idx = MagicMock()
    idx.search.return_value = results
    return idx


# ---------------------------------------------------------------------------
# Fake request/response transport for GikiHandler
# ---------------------------------------------------------------------------


class FakeWfile:
    def __init__(self):
        self.data = b""

    def write(self, b):
        self.data += b


class FakeRfile:
    def __init__(self, request_line: str = "GET / HTTP/1.1"):
        self._lines = [
            request_line.encode() + b"\r\n",
            b"Host: localhost\r\n",
            b"\r\n",
        ]
        self._idx = 0

    def readline(self, *args):
        if self._idx < len(self._lines):
            line = self._lines[self._idx]
            self._idx += 1
            return line
        return b""


def _invoke_handler(handler_cls, path: str, store, index):
    """Instantiate GikiHandler and invoke do_GET, returning (status, headers, body)."""
    h = object.__new__(handler_cls)
    h.root = Path(".")
    h.store = store
    h.search_index = index
    h._html_bytes = HTML_FRONTEND.encode("utf-8")

    h.path = path
    h.requestline = f"GET {path} HTTP/1.1"
    h.request_version = "HTTP/1.1"
    h.command = "GET"
    h.client_address = ("127.0.0.1", 12345)
    h.wfile = FakeWfile()
    h.rfile = FakeRfile()

    h.do_GET()

    # Parse response from wfile buffer
    raw = h.wfile.data
    header_end = raw.find(b"\r\n\r\n")
    header_block = raw[:header_end].decode("utf-8")
    body = raw[header_end + 4:]

    status_line = header_block.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])

    headers = {}
    for line in header_block.split("\r\n")[1:]:
        k, v = line.split(": ", 1)
        headers[k] = v

    return status_code, headers, body


# ---------------------------------------------------------------------------
# Tests: HTML frontend
# ---------------------------------------------------------------------------


class TestHTMLFrontend:
    def test_html_contains_d3_cdn(self):
        assert "d3/7.9.0/d3.min.js" in HTML_FRONTEND

    def test_html_contains_marked_cdn(self):
        assert "marked/12.0.0/marked.min.js" in HTML_FRONTEND

    def test_html_has_graph_and_search(self):
        assert "forceSimulation" in HTML_FRONTEND
        assert "/api/search" in HTML_FRONTEND
        assert "/api/graph" in HTML_FRONTEND


# ---------------------------------------------------------------------------
# Tests: API endpoints via handler
# ---------------------------------------------------------------------------


class TestApiPages:
    def test_pages_list(self):
        store = _make_store({"hello": _SAMPLE_PAGE})
        idx = _make_index([])
        status, headers, body = _invoke_handler(GikiHandler, "/api/pages", store, idx)

        assert status == 200
        assert "application/json" in headers.get("Content-Type", "")
        data = json.loads(body)
        assert len(data) == 1
        assert data[0]["slug"] == "hello"
        assert data[0]["title"] == "Hello World"
        assert data[0]["tags"] == ["test", "demo"]


class TestApiPage:
    def test_page_detail(self):
        store = _make_store({"hello": _SAMPLE_PAGE})
        idx = _make_index([])
        status, headers, body = _invoke_handler(GikiHandler, "/api/page/hello", store, idx)

        assert status == 200
        data = json.loads(body)
        assert data["slug"] == "hello"
        assert data["title"] == "Hello World"
        assert "other-page" in data["body"]
        assert data["aliases"] == ["hw"]
        assert data["tags"] == ["test", "demo"]
        assert any(lk["target"] == "other-page" for lk in data["links"])

    def test_page_not_found(self):
        store = _make_store({})
        idx = _make_index([])
        status, _, _ = _invoke_handler(GikiHandler, "/api/page/nope", store, idx)
        assert status == 404


class TestApiSearch:
    def test_search_returns_results(self):
        store = _make_store({"hello": _SAMPLE_PAGE})
        idx = _make_index([("hello", 3.14)])
        status, _, body = _invoke_handler(
            GikiHandler, "/api/search?q=hello", store, idx
        )

        assert status == 200
        data = json.loads(body)
        assert len(data) == 1
        assert data[0]["slug"] == "hello"
        assert abs(data[0]["score"] - 3.14) < 0.01

    def test_search_empty_query(self):
        store = _make_store({})
        idx = _make_index([])
        status, _, body = _invoke_handler(GikiHandler, "/api/search?q=", store, idx)
        assert status == 200
        assert json.loads(body) == []


class TestApiGraph:
    def test_graph_nodes_and_links(self):
        page_a = WikiPage(
            title="Page A", aliases=[], tags=[], created="2024-01-01T00:00:00+00:00",
            updated="2024-01-01T00:00:00+00:00", sources=[],
            body="Link to [[page-b]].", links=[WikiLink(target="page-b", display=None, link_type=None)],
        )
        page_b = WikiPage(
            title="Page B", aliases=[], tags=[], created="2024-01-01T00:00:00+00:00",
            updated="2024-01-01T00:00:00+00:00", sources=[],
            body="No links.", links=[],
        )
        store = _make_store({"page-a": page_a, "page-b": page_b})
        idx = _make_index([])
        status, _, body = _invoke_handler(GikiHandler, "/api/graph", store, idx)

        assert status == 200
        data = json.loads(body)
        ids = {n["id"] for n in data["nodes"]}
        assert ids == {"page-a", "page-b"}
        assert len(data["links"]) == 1
        assert data["links"][0]["source"] == "page-a"
        assert data["links"][0]["target"] == "page-b"

    def test_graph_ignores_missing_targets(self):
        page_a = WikiPage(
            title="Page A", aliases=[], tags=[], created="2024-01-01T00:00:00+00:00",
            updated="2024-01-01T00:00:00+00:00", sources=[],
            body="Link to [[missing]].", links=[WikiLink(target="missing", display=None, link_type=None)],
        )
        store = _make_store({"page-a": page_a})
        idx = _make_index([])
        status, _, body = _invoke_handler(GikiHandler, "/api/graph", store, idx)

        data = json.loads(body)
        assert len(data["nodes"]) == 1
        assert data["links"] == []


class TestServeHTML:
    def test_root_serves_html(self):
        store = _make_store({})
        idx = _make_index([])
        status, headers, body = _invoke_handler(GikiHandler, "/", store, idx)
        assert status == 200
        assert "text/html" in headers.get("Content-Type", "")
        assert b"d3.min.js" in body


class TestNotFound:
    def test_unknown_path_404(self):
        store = _make_store({})
        idx = _make_index([])
        status, _, _ = _invoke_handler(GikiHandler, "/nope", store, idx)
        assert status == 404


# ---------------------------------------------------------------------------
# Tests: CLI integration
# ---------------------------------------------------------------------------


class TestServeCLI:
    def test_serve_help(self):
        from typer.testing import CliRunner
        from giki.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        out = result.stdout
        assert "--port" in out
        assert "--host" in out
        assert "--root" in out
