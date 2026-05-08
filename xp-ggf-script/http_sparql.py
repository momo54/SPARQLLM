from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from rdflib import BNode, Graph, Literal, URIRef


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class HttpMetrics:
    call_count: int = 0
    upload_bytes: int = 0
    download_bytes: int = 0


class LocalSparqlServer:
    def __init__(
        self,
        repo_root: Path,
        kb_ttl: str,
        qa_ttl: str = "",
        host: str = "127.0.0.1",
        port: int | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.kb_ttl = kb_ttl
        self.qa_ttl = qa_ttl
        self.host = host
        self.port = find_free_port() if port is None else port
        self.process: subprocess.Popen[str] | None = None

    @property
    def endpoint_url(self) -> str:
        return f"http://{self.host}:{self.port}/sparql"

    @property
    def health_url(self) -> str:
        return f"http://{self.host}:{self.port}/health"

    def start(self, timeout_s: float = 20.0) -> None:
        script_path = self.repo_root / "scripts" / "mini_rdflib_sparql_server.py"
        cmd = [
            sys.executable,
            str(script_path),
            "--kb-ttl",
            self.kb_ttl,
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        if self.qa_ttl:
            cmd.extend(["--qa-ttl", self.qa_ttl])
        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Local SPARQL server exited before becoming healthy.")
            try:
                resp = requests.get(self.health_url, timeout=0.5)
                if resp.status_code == 200 and resp.text.strip() == "ok":
                    return
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("Timed out waiting for local SPARQL server health check.")

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None


class HttpSparqlClient:
    def __init__(self, endpoint_url: str, simulated_latency_ms: float = 0.0) -> None:
        self.endpoint_url = endpoint_url
        self.metrics = HttpMetrics()
        self.simulated_latency_s = max(0.0, float(simulated_latency_ms)) / 1000.0

    def select(self, query: str, timeout: float = 30.0) -> list[dict[str, Any]]:
        if self.simulated_latency_s > 0:
            time.sleep(self.simulated_latency_s)
        data = {"query": query}
        resp = requests.post(
            self.endpoint_url,
            data=data,
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout,
        )
        body = resp.request.body or b""
        if not isinstance(body, (bytes, bytearray)):
            body = str(body).encode("utf-8")
        self.metrics.call_count += 1
        self.metrics.upload_bytes += len((resp.request.url or "").encode("utf-8")) + len(body)
        self.metrics.download_bytes += len(resp.content or b"")
        resp.raise_for_status()
        payload = resp.json()
        vars_list = payload.get("head", {}).get("vars", [])
        out: list[dict[str, Any]] = []
        for binding in payload.get("results", {}).get("bindings", []):
            row: dict[str, Any] = {}
            for var in vars_list:
                cell = binding.get(var)
                if cell is None:
                    continue
                row[var] = self._decode_cell(cell)
            out.append(row)
        return out

    @staticmethod
    def _decode_cell(cell: dict[str, Any]) -> Any:
        cell_type = cell.get("type")
        value = cell.get("value", "")
        if cell_type == "uri":
            return URIRef(value)
        if cell_type == "bnode":
            return BNode(value)
        datatype = cell.get("datatype")
        lang = cell.get("xml:lang")
        return Literal(value, lang=lang, datatype=URIRef(datatype) if datatype else None)

    def rows_to_graph(self, rows: list[dict[str, Any]], s_var: str = "s", p_var: str = "p", o_var: str = "o") -> Graph:
        graph = Graph()
        for row in rows:
            s = row.get(s_var)
            p = row.get(p_var)
            o = row.get(o_var)
            if s is None or p is None or o is None:
                continue
            graph.add((s, p, o))
        return graph


def sparql_iri_values(var_name: str, iris: list[str]) -> str:
    values = " ".join(f"<{iri}>" for iri in iris if iri)
    return f"VALUES ?{var_name} {{ {values} }}"
