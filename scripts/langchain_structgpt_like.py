#!/usr/bin/env python3
"""LangChain orchestration for a minimal StructGPT-like Wikidata workflow.

Pipeline:
1. Ask the LLM to identify the anchor entity mention in the question.
2. Query Wikidata wbsearchentities for this anchor mention.
3. Ask the LLM to choose the best Wikidata candidate.
4. Query Wikidata SPARQL for related entities.
5. Ask the LLM to produce a compact answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.langchain_wikidata_direct import (
    USER_AGENT,
    build_llm,
    load_environment,
    read_request_defaults,
)

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"


def _new_metrics() -> dict[str, Any]:
    return {
        "wikidata_call_count": 0,
        "upload_bytes": 0,
        "download_bytes": 0,
        "llm_call_count": 0,
        "by_endpoint": {
            "wbsearchentities": {"calls": 0, "upload_bytes": 0, "download_bytes": 0},
            "sparql": {"calls": 0, "upload_bytes": 0, "download_bytes": 0},
        },
    }


def _record_http(metrics: dict[str, Any], endpoint: str, response: requests.Response) -> None:
    request = response.request
    upload_bytes = len((request.url or "").encode("utf-8"))
    if request.body:
        body = request.body if isinstance(request.body, (bytes, bytearray)) else str(request.body).encode("utf-8")
        upload_bytes += len(body)
    download_bytes = len(response.content or b"")

    metrics["wikidata_call_count"] += 1
    metrics["upload_bytes"] += upload_bytes
    metrics["download_bytes"] += download_bytes
    metrics["by_endpoint"][endpoint]["calls"] += 1
    metrics["by_endpoint"][endpoint]["upload_bytes"] += upload_bytes
    metrics["by_endpoint"][endpoint]["download_bytes"] += download_bytes


def _extract_anchor_mention(llm: Any, question: str, metrics: dict[str, Any]) -> str:
    metrics["llm_call_count"] += 1
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You extract the main anchor entity mention from a question. Output valid JSON only."),
            (
                "human",
                """
Question: {question}

Return exactly one JSON object:
{{
  "anchor": "entity mention"
}}

Rules:
- Extract the single main entity the user wants to compare against.
- Preserve the original surface form.
- No markdown.
- No extra keys.
""",
            ),
        ]
    )
    chain = prompt | llm | parser
    payload = chain.invoke({"question": question})
    anchor = payload.get("anchor") if isinstance(payload, dict) else ""
    return str(anchor).strip()


def _search_entity(session: requests.Session, mention: str, language: str, limit: int, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    response = session.get(
        WIKIDATA_API_URL,
        params={
            "action": "wbsearchentities",
            "format": "json",
            "search": mention,
            "language": language,
            "limit": int(limit),
        },
        timeout=20,
    )
    response.raise_for_status()
    _record_http(metrics, "wbsearchentities", response)
    data = response.json()
    return data.get("search", [])


def _choose_entity(llm: Any, question: str, mention: str, candidates: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any] | None:
    if not candidates:
        return None

    metrics["llm_call_count"] += 1
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You choose the best Wikidata entity candidate. Output valid JSON only."),
            (
                "human",
                """
Question: {question}
Anchor mention: {mention}
Candidates JSON: {candidates_json}

Return exactly one JSON object:
{{
  "chosen_qid": "Q..."
}}

Rules:
- Pick one qid from the candidate list only.
- Prefer exact person-name matches.
- No extra keys.
- No markdown.
""",
            ),
        ]
    )
    chain = prompt | llm | parser
    payload = chain.invoke(
        {
            "question": question,
            "mention": mention,
            "candidates_json": json.dumps(candidates, ensure_ascii=False),
        }
    )
    chosen_qid = str(payload.get("chosen_qid", "")).strip() if isinstance(payload, dict) else ""
    for item in candidates:
        if str(item.get("id", "")).strip() == chosen_qid:
            return item
    return candidates[0]


def _expand_related(session: requests.Session, qid: str, language: str, limit: int, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    sparql = f"""
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?similar ?similar_label WHERE {{
  wd:{qid} wdt:P136 ?genre .
  ?similar wdt:P136 ?genre ;
           wdt:P31 wd:Q5 .
  wd:{qid} wdt:P106 ?occ .
  ?similar wdt:P106 ?occ .
  FILTER(?similar != wd:{qid})
  ?similar rdfs:label ?similar_label .
  FILTER(LANG(?similar_label) = "{language}")
}}
LIMIT {int(limit)}
""".strip()

    response = session.get(
        WIKIDATA_SPARQL_URL,
        params={"query": sparql, "format": "json"},
        timeout=30,
        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    _record_http(metrics, "sparql", response)
    bindings = response.json().get("results", {}).get("bindings", [])

    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(bindings, start=1):
        rows.append(
            {
                "rank": idx,
                "label": row.get("similar_label", {}).get("value", ""),
                "entity": row.get("similar", {}).get("value", ""),
                "score": round(1.0 / float(idx), 6),
            }
        )
    return rows


def _compose_answer(llm: Any, question: str, anchor_label: str, candidates: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    metrics["llm_call_count"] += 1
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You write a concise answer from a ranked candidate list. Output valid JSON only."),
            (
                "human",
                """
Question: {question}
Anchor entity: {anchor_label}
Candidates JSON: {candidates_json}

Return exactly one JSON object:
{{
  "answer": "short answer"
}}

Rules:
- Mention 3 to 5 candidates.
- Keep the answer factual and concise.
- No markdown.
- No extra keys.
""",
            ),
        ]
    )
    chain = prompt | llm | parser
    payload = chain.invoke(
        {
            "question": question,
            "anchor_label": anchor_label,
            "candidates_json": json.dumps(candidates[:5], ensure_ascii=False),
        }
    )
    return str(payload.get("answer", "")).strip() if isinstance(payload, dict) else ""


def run_pipeline(question: str, language: str, provider: str, model: str, temperature: float, groq_api_key: str = "") -> dict[str, Any]:
    llm = build_llm(provider=provider, model=model, temperature=temperature, groq_api_key=groq_api_key)
    metrics = _new_metrics()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    anchor = _extract_anchor_mention(llm, question, metrics)
    if not anchor:
        raise RuntimeError("The LLM did not return an anchor mention.")

    candidates = _search_entity(session, anchor, language, 5, metrics)
    chosen = _choose_entity(llm, question, anchor, candidates, metrics)
    if not chosen:
        raise RuntimeError("No Wikidata candidate was selected.")

    qid = str(chosen.get("id", "")).strip()
    label = str(chosen.get("label", anchor)).strip() or anchor
    related = _expand_related(session, qid, language, 10, metrics)
    answer = _compose_answer(llm, question, label, related, metrics)

    return {
        "question": question,
        "anchor_mention": anchor,
        "anchor_qid": qid,
        "anchor_label": label,
        "answer": answer,
        "candidates": related,
        "metrics": metrics,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangChain StructGPT-like Wikidata pipeline.")
    parser.add_argument("--question", default="I am looking for science-fiction authors similar to Isaac Asimov")
    parser.add_argument("--language", default="en")
    parser.add_argument("--config", default="config.ini")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--provider", choices=["ollama", "groq"], default="groq")
    parser.add_argument("--model", default="")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--out", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    load_environment(args.env_file)
    defaults = read_request_defaults(args.config)

    if args.model:
        model = args.model
    elif args.provider == "groq":
        model = defaults.get("SLM-GROQ-MODEL") or "llama-3.3-70b-versatile"
    else:
        model = defaults.get("SLM-OLLAMA-MODEL") or "llama3.1:8b"

    if args.temperature is not None:
        temperature = args.temperature
    else:
        raw_temp = defaults.get("SLM-LLM-TEMPERATURE", "")
        try:
            temperature = float(raw_temp) if raw_temp else 0.0
        except ValueError:
            temperature = 0.0

    try:
        result = run_pipeline(
            question=args.question,
            language=args.language,
            provider=args.provider,
            model=model,
            temperature=temperature,
            groq_api_key=defaults.get("GROQ_API_KEY", ""),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))