#!/usr/bin/env python3
"""Minimal HTTP SPARQL endpoint backed by RDFLib.

Loads two Turtle knowledge graphs (MetaQA QA + KB by default) into one
RDFLib graph and serves SPARQL SELECT queries over HTTP.

Endpoints:
- GET  /sparql?query=...
- POST /sparql with form field "query"
- GET  /health

Response format:
- SPARQL JSON results for SELECT queries

Example:
  venv/bin/python scripts/mini_rdflib_sparql_server.py \
      --qa-ttl data/metaqa/MetaQA/qa_2hop.ttl \
      --kb-ttl data/metaqa/MetaQA/kb.ttl \
      --host 127.0.0.1 --port 3031
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rdflib import ConjunctiveGraph


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mini HTTP SPARQL endpoint using RDFLib")
    p.add_argument("--qa-ttl", default="", help="Optional path to QA Turtle")
    p.add_argument("--kb-ttl", default="data/metaqa/MetaQA/kb.ttl", help="Path to KB Turtle")
    p.add_argument("--host", default="127.0.0.1", help="Bind host")
    p.add_argument("--port", type=int, default=3031, help="Bind port")
    return p.parse_args()


def _literal_json_value(term) -> dict[str, str]:
    if term is None:
        return {"type": "literal", "value": ""}

    if getattr(term, "datatype", None):
        return {
            "type": "literal",
            "datatype": str(term.datatype),
            "value": str(term),
        }

    if getattr(term, "language", None):
        return {
            "type": "literal",
            "xml:lang": str(term.language),
            "value": str(term),
        }

    return {"type": "literal", "value": str(term)}


def _binding_json(term) -> dict[str, str]:
    term_type = getattr(term, "__class__", type(term)).__name__.lower()

    if "uri" in term_type or term_type == "uriref":
        return {"type": "uri", "value": str(term)}
    if "bnode" in term_type:
        return {"type": "bnode", "value": str(term)}
    return _literal_json_value(term)


def result_to_sparql_json(result) -> dict:
    vars_list = [str(v) for v in getattr(result, "vars", [])]
    bindings = []

    for row in result:
        row_binding = {}
        for var in vars_list:
            val = row.get(var)
            if val is None:
                continue
            row_binding[var] = _binding_json(val)
        bindings.append(row_binding)

    return {
        "head": {"vars": vars_list},
        "results": {"bindings": bindings},
    }


def make_handler(graph: ConjunctiveGraph):
    class SparqlHandler(BaseHTTPRequestHandler):
        server_version = "MiniRDFLibSPARQL/0.1"

        def _send_json(self, payload: dict, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/sparql-results+json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_text(self, text: str, status: int = 200) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)

            if parsed.path == "/health":
                self._send_text("ok\n", status=200)
                return

            if parsed.path != "/sparql":
                self._send_text("Not Found\n", status=404)
                return

            params = parse_qs(parsed.query)
            query = (params.get("query") or [""])[0]
            if not query.strip():
                self._send_text("Missing 'query' parameter\n", status=400)
                return

            self._execute_query(query)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/sparql":
                self._send_text("Not Found\n", status=404)
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            form = parse_qs(body)
            query = (form.get("query") or [""])[0]

            if not query.strip():
                self._send_text("Missing form field 'query'\n", status=400)
                return

            self._execute_query(query)

        def _execute_query(self, query: str) -> None:
            try:
                q_upper = query.lstrip().upper()
                if not q_upper.startswith("SELECT") and " SELECT " not in q_upper:
                    self._send_text("Only SELECT queries are supported\n", status=400)
                    return

                result = graph.query(query)
                payload = result_to_sparql_json(result)
                self._send_json(payload, status=200)
            except Exception as exc:  # pragma: no cover
                self._send_json({"error": str(exc)}, status=500)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            # Keep console logs concise.
            print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    return SparqlHandler


def main() -> None:
    args = parse_args()

    qa_path = Path(args.qa_ttl) if args.qa_ttl else None
    kb_path = Path(args.kb_ttl) if args.kb_ttl else None

    if kb_path is None or not kb_path.exists():
        raise FileNotFoundError(f"KB file not found: {kb_path}")
    if qa_path is not None and not qa_path.exists():
        raise FileNotFoundError(f"QA file not found: {qa_path}")

    g = ConjunctiveGraph()
    g.parse(str(kb_path), format="ttl")
    if qa_path is not None:
        g.parse(str(qa_path), format="ttl")

    print(f"Loaded triples: {len(g):,}")
    print(f"Serving SPARQL endpoint at http://{args.host}:{args.port}/sparql")
    print(f"Health check at         http://{args.host}:{args.port}/health")

    handler = make_handler(g)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
