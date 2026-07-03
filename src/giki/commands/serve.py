"""`giki serve` — local web UI with D3 graph visualization and search."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import typer


# ---------------------------------------------------------------------------
# Embedded HTML frontend
# ---------------------------------------------------------------------------

HTML_FRONTEND = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>giki serve</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.0/marked.min.js"></script>
<style>
  :root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --border: #0f3460;
    --text: #e4e4e4;
    --text-dim: #a0a0b0;
    --accent: #e94560;
    --link: #53c1de;
    --node: #53c1de;
    --node-hover: #e94560;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); }
  #app { display: flex; height: 100vh; }
  #sidebar {
    width: 320px; min-width: 260px; background: var(--surface);
    border-right: 1px solid var(--border); display: flex; flex-direction: column;
  }
  #sidebar h1 { padding: 16px; font-size: 18px; border-bottom: 1px solid var(--border); }
  #search-box { padding: 12px; border-bottom: 1px solid var(--border); }
  #search-box input {
    width: 100%; padding: 8px 10px; border-radius: 4px; border: 1px solid var(--border);
    background: var(--bg); color: var(--text); font-size: 14px; outline: none;
  }
  #search-box input:focus { border-color: var(--accent); }
  #search-results {
    flex: 1; overflow-y: auto; padding: 8px 0;
  }
  .result-item {
    padding: 8px 16px; cursor: pointer; font-size: 14px; border-bottom: 1px solid var(--border);
  }
  .result-item:hover { background: var(--border); }
  .result-item .score { color: var(--text-dim); font-size: 12px; }
  #viewer {
    flex: 1; overflow-y: auto; padding: 32px 48px;
  }
  #viewer h1 { font-size: 28px; margin-bottom: 16px; color: var(--accent); }
  #viewer .meta { color: var(--text-dim); font-size: 13px; margin-bottom: 24px; }
  #viewer .body { line-height: 1.7; font-size: 15px; }
  #viewer .body h1, #viewer .body h2, #viewer .body h3 { margin-top: 20px; margin-bottom: 8px; color: var(--link); }
  #viewer .body a { color: var(--link); }
  #viewer .body code { background: var(--surface); padding: 2px 6px; border-radius: 3px; font-size: 13px; }
  #viewer .body pre { background: var(--surface); padding: 12px; border-radius: 4px; overflow-x: auto; margin: 12px 0; }
  #viewer .body pre code { background: none; padding: 0; }
  #graph-container {
    flex: 1; position: relative; border-top: 1px solid var(--border);
  }
  #graph-container svg { width: 100%; height: 100%; display: block; }
  #graph-container .node circle { fill: var(--node); stroke: var(--bg); stroke-width: 1.5px; cursor: pointer; }
  #graph-container .node circle:hover { fill: var(--node-hover); }
  #graph-container .node text { fill: var(--text-dim); font-size: 10px; pointer-events: none; }
  #graph-container .link { stroke: var(--border); stroke-opacity: 0.6; stroke-width: 1px; }
  .empty-msg { color: var(--text-dim); padding: 24px 16px; font-size: 14px; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <h1>giki</h1>
    <div id="search-box"><input id="search-input" type="text" placeholder="Search wiki pages..."/></div>
    <div id="search-results"></div>
  </div>
  <div style="flex:1; display:flex; flex-direction:column;">
    <div id="viewer">
      <p class="empty-msg">Click a node or search result to view a page.</p>
    </div>
    <div id="graph-container"></div>
  </div>
</div>
<script>
const $ = (s) => document.querySelector(s);
const state = { pages: [], graph: null, currentSlug: null };

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}

// --- Pages list ---
async function loadPages() {
  state.pages = await fetchJSON('/api/pages');
}

// --- Search ---
let searchTimer = null;
$('#search-input').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (!q) { renderAllPages(); return; }
  searchTimer = setTimeout(() => doSearch(q), 250);
});

async function doSearch(q) {
  const results = await fetchJSON('/api/search?q=' + encodeURIComponent(q));
  const container = $('#search-results');
  container.innerHTML = '';
  if (!results.length) {
    container.innerHTML = '<p class="empty-msg">No results.</p>';
    return;
  }
  for (const r of results) {
    const page = state.pages.find(p => p.slug === r.slug);
    const div = document.createElement('div');
    div.className = 'result-item';
    div.innerHTML = '<div>' + (page ? page.title : r.slug) + '</div><div class="score">score: ' + r.score.toFixed(3) + '</div>';
    div.addEventListener('click', () => viewPage(r.slug));
    container.appendChild(div);
  }
}

function renderAllPages() {
  const container = $('#search-results');
  container.innerHTML = '';
  for (const p of state.pages) {
    const div = document.createElement('div');
    div.className = 'result-item';
    div.textContent = p.title;
    div.addEventListener('click', () => viewPage(p.slug));
    container.appendChild(div);
  }
}

// --- Page viewer ---
async function viewPage(slug) {
  state.currentSlug = slug;
  const page = await fetchJSON('/api/page/' + encodeURIComponent(slug));
  const tags = (page.tags || []).map(t => '#' + t).join(' ');
  const aliases = (page.aliases || []).length ? 'Aliases: ' + page.aliases.join(', ') : '';
  const meta = [tags, aliases].filter(Boolean).join(' | ');
  $('#viewer').innerHTML =
    '<h1>' + page.title + '</h1>' +
    (meta ? '<div class="meta">' + meta + '</div>' : '') +
    '<div class="body">' + marked.parse(page.body || '') + '</div>';
}

// --- Graph ---
async function loadGraph() {
  state.graph = await fetchJSON('/api/graph');
  drawGraph();
}

function drawGraph() {
  const container = $('#graph-container');
  const width = container.clientWidth;
  const height = container.clientHeight || 400;
  container.innerHTML = '';

  const { nodes, links } = state.graph;
  if (!nodes.length) return;

  const svg = d3.select(container).append('svg')
    .attr('width', width).attr('height', height);

  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide(24));

  const link = svg.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('class', 'link');

  const node = svg.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append('circle').attr('r', 8)
    .on('click', (e, d) => viewPage(d.id));

  node.append('text')
    .attr('dx', 12).attr('dy', 4)
    .text(d => d.title);

  sim.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
  });
}

window.addEventListener('resize', () => { if (state.graph) drawGraph(); });

// --- Init ---
(async () => {
  await loadPages();
  renderAllPages();
  await loadGraph();
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class GikiHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the giki web UI."""

    root: Path = Path(".")
    store = None
    search_index = None
    _html_bytes: bytes = b""

    def log_message(self, format, *args):  # noqa: A002 — override stdlib
        """Suppress default access log."""

    def do_GET(self):  # noqa: N802 — stdlib naming
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_html()
        elif path == "/api/pages":
            self._serve_pages()
        elif path.startswith("/api/page/"):
            slug = path[len("/api/page/"):]
            self._serve_page(slug)
        elif path == "/api/search":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            self._serve_search(q)
        elif path == "/api/graph":
            self._serve_graph()
        else:
            self.send_error(404)

    # ---- helpers ----------------------------------------------------------

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- endpoints --------------------------------------------------------

    def _serve_html(self):
        self._send_html(self._html_bytes)

    def _serve_pages(self):
        pages = []
        for slug in self.store.list_pages():
            try:
                raw = self.store.read(slug)
                from ..wiki.parser import parse_page
                page = parse_page(raw)
                pages.append({"slug": slug, "title": page.title, "tags": page.tags})
            except Exception:
                # Skip pages that fail to parse (e.g. missing frontmatter)
                pages.append({"slug": slug, "title": slug, "tags": []})
        self._send_json(pages)

    def _serve_page(self, slug: str):
        if not self.store.exists(slug):
            self.send_error(404, f"page not found: {slug}")
            return
        raw = self.store.read(slug)
        from ..wiki.parser import parse_page

        try:
            page = parse_page(raw)
        except Exception as e:
            self._send_json({
                "slug": slug,
                "title": slug,
                "body": f"*This page could not be parsed: {e}*\n\n```\n{raw[:500]}\n```",
                "aliases": [],
                "tags": [],
                "links": [],
            })
            return

        self._send_json({
            "slug": slug,
            "title": page.title,
            "body": page.body,
            "aliases": page.aliases,
            "tags": page.tags,
            "links": [{"target": lk.target, "display": lk.display, "type": lk.link_type} for lk in page.links],
        })

    def _serve_search(self, q: str):
        if not q.strip():
            self._send_json([])
            return
        results = self.search_index.search(q)
        self._send_json([{"slug": slug, "score": score} for slug, score in results])

    def _serve_graph(self):
        from ..wiki.parser import parse_page

        slugs = set(self.store.list_pages())
        nodes = []
        links = []
        for slug in sorted(slugs):
            try:
                raw = self.store.read(slug)
                page = parse_page(raw)
                nodes.append({"id": slug, "title": page.title})
                for lk in page.links:
                    target = lk.target
                    if target in slugs and target != slug:
                        links.append({"source": slug, "target": target})
            except Exception:
                # Skip pages that fail to parse — still add as a node with no links
                nodes.append({"id": slug, "title": slug})
        self._send_json({"nodes": nodes, "links": links})


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def serve_command(
    port: int = typer.Option(8080, "--port", help="Port to listen on."),
    host: str = typer.Option("localhost", "--host", help="Host to bind to."),
    root: Path = typer.Option(Path("."), "--root", help="Wiki project root."),
) -> None:
    """Start the giki local web UI with graph visualization and search."""
    from ..config import load_config
    from ..search import SearchIndex
    from ..wiki.store import WikiStore

    root = Path(root).resolve()

    # Load config for slug settings
    try:
        cfg = load_config(root)
        slug_pattern = cfg.wiki.enforce_slug_pattern
        max_slug_length = cfg.wiki.max_slug_length
    except Exception:
        slug_pattern = r"^[a-z0-9-]+$"
        max_slug_length = 80

    store = WikiStore(root, slug_pattern=slug_pattern, max_slug_length=max_slug_length)

    # Build / load search index
    idx = SearchIndex(root)
    if not idx.load():
        idx.build(store.wiki_dir)
        idx.save()

    # Configure handler
    GikiHandler.root = root
    GikiHandler.store = store
    GikiHandler.search_index = idx
    GikiHandler._html_bytes = HTML_FRONTEND.encode("utf-8")

    server = HTTPServer((host, port), GikiHandler)
    from ..console import console

    console.print(f"[bold]giki serve[/bold] listening on [link]http://{host}:{port}[/link]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        console.print("\n[dim]Server stopped.[/dim]")
