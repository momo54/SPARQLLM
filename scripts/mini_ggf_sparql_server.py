#!/usr/bin/env python3
"""Minimal HTTP SPARQL endpoint backed by the SPARQLLM/GGF store.

This mirrors scripts/mini_rdflib_sparql_server.py, but executes queries against
SPARQLLM.udf.SPARQLLM.store after registering UDFs from a SPARQLLM config file.

Endpoints:
- GET  /sparql?query=...
- POST /sparql with form field "query"
- GET  /health

Response format:
- SPARQL JSON results for SELECT queries

Example:
  python scripts/mini_ggf_sparql_server.py \
      --config config.ini \
      --load data/metaqa/MetaQA/kb.ttl \
      --format turtle \
      --host 127.0.0.1 \
      --port 3032
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.read_rdf import load_rdf_file


SELECT_QUERY_RE = re.compile(r"(^|\s)SELECT(\s|$)", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mini HTTP SPARQL endpoint using SPARQLLM/GGF")
    p.add_argument("--config", required=True, help="SPARQLLM config.ini with [Associations]")
    p.add_argument("--load", default="", help="Optional RDF file to preload into the SPARQLLM store")
    p.add_argument("--format", default="turtle", help="RDF format for --load")
    p.add_argument("--host", default="127.0.0.1", help="Bind host")
    p.add_argument("--port", type=int, default=3032, help="Bind port")
    p.add_argument(
        "--keep-intermediate-graphs",
        action="store_true",
        help="Keep GGF-created named graphs between requests instead of clearing them before each query.",
    )
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
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


def _context_identifier_set() -> set[str]:
    return {str(ctx.identifier) for ctx in store.contexts()}


def _clear_dynamic_contexts(base_context_ids: set[str]) -> None:
    for ctx in list(store.contexts()):
        if str(ctx.identifier) not in base_context_ids:
            store.remove_graph(ctx)


def make_handler(base_context_ids: set[str], keep_intermediate_graphs: bool, query_lock: threading.Lock):
    class GgfSparqlHandler(BaseHTTPRequestHandler):
        server_version = "MiniGGFSPARQL/0.1"

        def _send_json(self, payload: dict, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/sparql-results+json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
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
                if SELECT_QUERY_RE.search(query) is None:
                    self._send_text("Only SELECT queries are supported\n", status=400)
                    return

                started = time.perf_counter()
                with query_lock:
                    if not keep_intermediate_graphs:
                        _clear_dynamic_contexts(base_context_ids)
                    result = store.query(query)
                    payload = result_to_sparql_json(result)
                elapsed = time.perf_counter() - started
                self._send_json(
                    payload,
                    status=200,
                    extra_headers={"X-SPARQLLM-Execution-Wall-Time-S": f"{elapsed:.6f}"},
                )
            except Exception as exc:  # pragma: no cover
                logging.exception("GGF SPARQL query failed")
                self._send_json({"error": str(exc)}, status=500)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            logging.info("[%s] %s %s", self.log_date_time_string(), self.address_string(), fmt % args)

    return GgfSparqlHandler


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    config_path = Path(args.config)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    ConfigSingleton.reset_instance()
    ConfigSingleton(config_file=str(config_path))

    loaded_graph_uri = None
    if args.load:
        load_path = Path(args.load)
        if not load_path.exists():
            raise FileNotFoundError(f"RDF file not found: {load_path}")
        loaded_graph_uri = load_rdf_file(str(load_path), args.format)
        logging.info("Loaded graph %s from %s", loaded_graph_uri, load_path)

    base_context_ids = _context_identifier_set()
    logging.info("Base contexts preserved between requests: %s", sorted(base_context_ids))

    query_lock = threading.Lock()
    handler = make_handler(base_context_ids, args.keep_intermediate_graphs, query_lock)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"Serving GGF SPARQL endpoint at http://{args.host}:{args.port}/sparql")
    print(f"Health check at             http://{args.host}:{args.port}/health")
    if loaded_graph_uri is not None:
        print(f"Loaded graph URI:           {loaded_graph_uri}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
