#!/usr/bin/env python3
"""LangChain equivalent of `wikidata-summarize-prompt.sparql`.

Pipeline:
1) Ask an LLM for a list of author names for a topic.
2) Query Wikidata `wbsearchentities` for each name.
3) Ask an LLM to rank/select the best Wikidata entity.
4) Query Wikidata SPARQL endpoint for a 1-hop direct-property schema walk.
5) Ask an LLM to summarize the extracted facts.

Usage example:
  python3 scripts/langchain_wikidata_direct.py \
    --topic "well-known science-fiction authors" \
        --provider ollama \
    --model llama3.1:8b \
    --language en \
    --count 10

Groq example:
    export GROQ_API_KEY="..."
    python3 scripts/langchain_wikidata_direct.py \
        --topic "well-known science-fiction authors" \
        --provider groq \
        --model llama-3.3-70b-versatile \
        --language en \
        --count 10
"""

from __future__ import annotations

import argparse
import configparser
import importlib
import json
import os
import re
import sys
from typing import Any

import requests
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "SPARQLLM-LangChain-Demo/0.1 (Wikidata direct query; mailto:you@example.org)"


def read_request_defaults(config_path: str) -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding="utf-8")

    req = parser["Requests"] if parser.has_section("Requests") else {}
    api = parser["ApiKeys"] if parser.has_section("ApiKeys") else {}

    def safe_get(section: Any, key: str) -> str:
        if hasattr(section, "get"):
            return str(section.get(key, "")).strip()
        return ""

    return {
        "SLM-GROQ-MODEL": safe_get(req, "SLM-GROQ-MODEL"),
        "SLM-OLLAMA-MODEL": safe_get(req, "SLM-OLLAMA-MODEL"),
        "SLM-LLM-TEMPERATURE": safe_get(req, "SLM-LLM-TEMPERATURE"),
        "GROQ_API_KEY": safe_get(api, "GROQ_API_KEY"),
    }


def load_environment(env_file: str) -> None:
    """Load environment variables from a .env file when available."""
    path = env_file.strip()
    if not path:
        return

    if load_dotenv is not None:
        load_dotenv(dotenv_path=path, override=False)

    # Fallback parser for .env files using shell-style `export KEY=value`.
    # Some dotenv versions/load modes may not expose these vars as expected.
    if not os.path.exists(path):
        return

    assign_re = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = assign_re.match(line)
            if not match:
                continue

            key, value = match.group(1), match.group(2)
            if key in os.environ and os.environ[key]:
                continue

            # Remove optional surrounding quotes.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ[key] = value


def get_chat_openai_class() -> type:
    """Resolve ChatOpenAI from available LangChain package.

    Prefer `langchain_openai` when installed, fallback to community package.
    """
    try:
        module = importlib.import_module("langchain_openai")
    except ImportError:
        module = importlib.import_module("langchain_community.chat_models")
    return getattr(module, "ChatOpenAI")


def build_llm(provider: str, model: str, temperature: float, groq_api_key: str = "") -> BaseChatModel:
    if provider == "ollama":
        return ChatOllama(model=model, temperature=temperature)

    if provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY", "").strip() or groq_api_key.strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set (env or config.ini [ApiKeys]).")

        ChatOpenAI = get_chat_openai_class()

        # Groq exposes an OpenAI-compatible endpoint.
        return ChatOpenAI(
            model_name=model,
            temperature=temperature,
            openai_api_key=api_key,
            openai_api_base="https://api.groq.com/openai/v1",
        )

    raise RuntimeError(f"Unsupported provider: {provider}")


def generate_author_names(llm: BaseChatModel, topic: str, count: int) -> list[str]:
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You extract concise entity names. Output must be valid JSON.",
            ),
            (
                "human",
                """
Return exactly one JSON object with this shape:
{{
    "authors": ["name 1", "name 2"]
}}

Requirements:
- Topic: {topic}
- Provide at least {count} distinct names.
- Use commonly known people only.
- No extra keys.
- No markdown.
""",
            ),
        ]
    )

    chain = prompt | llm | parser
    payload = chain.invoke({"topic": topic, "count": count})

    raw_authors = payload.get("authors", []) if isinstance(payload, dict) else []
    authors = [str(name).strip() for name in raw_authors if str(name).strip()]

    # Keep order while deduplicating.
    unique: list[str] = []
    seen = set()
    for name in authors:
        lowered = name.lower()
        if lowered not in seen:
            seen.add(lowered)
            unique.append(name)

    return unique[:count]


def wikidata_search_entities(session: requests.Session, name: str, language: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "search": name,
        "language": language,
        "limit": limit,
    }
    response = session.get(WIKIDATA_API_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data.get("search", [])


def choose_best_entity(
    llm: BaseChatModel,
    topic: str,
    author_name: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You rank Wikidata entity candidates and return valid JSON.",
            ),
            (
                "human",
                """
Task:
Select the best Wikidata candidate for the requested author and topic.

Requested author: {author_name}
Topic: {topic}
Candidates JSON: {candidates_json}

Return exactly one JSON object:
{{
    "chosen_qid": "Q..."
}}

Rules:
- Pick one qid from the candidates only.
- If uncertain, choose the candidate with the closest person label match.
- No other keys.
- No markdown.
""",
            ),
        ]
    )

    chain = prompt | llm | parser
    payload = chain.invoke(
        {
            "author_name": author_name,
            "topic": topic,
            "candidates_json": json.dumps(candidates, ensure_ascii=False),
        }
    )

    chosen_qid = payload.get("chosen_qid") if isinstance(payload, dict) else None
    if not chosen_qid:
        return candidates[0]

    chosen_qid = str(chosen_qid).strip()
    for item in candidates:
        if item.get("id") == chosen_qid:
            return item

    return candidates[0]


def wikidata_schema_walk(
    session: requests.Session,
    qid: str,
    language: str,
    limit: int,
) -> list[dict[str, str]]:
    sparql = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?p ?pLabel ?o ?oLabel
WHERE {{
  BIND(wd:{qid} AS ?entity)
  ?entity ?p ?o .
  FILTER(STRSTARTS(STR(?p), STR(wdt:)))
  OPTIONAL {{ ?o rdfs:label ?oLabel FILTER(LANG(?oLabel) = "{language}") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
}}
LIMIT {int(limit)}
""".strip()

    response = session.get(
        WIKIDATA_SPARQL_URL,
        params={"query": sparql, "format": "json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    bindings = data.get("results", {}).get("bindings", [])

    rows: list[dict[str, str]] = []
    for row in bindings:
        p = row.get("p", {}).get("value", "")
        p_label = row.get("pLabel", {}).get("value", "")
        o = row.get("o", {}).get("value", "")
        o_label = row.get("oLabel", {}).get("value", "")
        rows.append({"p": p, "pLabel": p_label, "o": o, "oLabel": o_label})

    return rows


def summarize_entity(
    llm: BaseChatModel,
    entity_label: str,
    qid: str,
    facts: list[dict[str, str]],
    language: str,
) -> str:
    parser = JsonOutputParser()

    compact_facts: list[dict[str, str]] = []
    for fact in facts[:40]:
        compact_facts.append(
            {
                "property": fact.get("pLabel") or fact.get("p"),
                "value": fact.get("oLabel") or fact.get("o"),
            }
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You write concise factual summaries from structured data. Output must be valid JSON.",
            ),
            (
                "human",
                """
Entity label: {entity_label}
Entity QID: {qid}
Language code for writing: {language}
Facts JSON: {facts_json}

Return exactly one JSON object:
{{
    "summary": "2-4 sentence factual summary"
}}

Rules:
- Use only the provided facts.
- Keep a neutral tone.
- No markdown.
- No extra keys.
""",
            ),
        ]
    )

    chain = prompt | llm | parser
    payload = chain.invoke(
        {
            "entity_label": entity_label,
            "qid": qid,
            "language": language,
            "facts_json": json.dumps(compact_facts, ensure_ascii=False),
        }
    )

    if isinstance(payload, dict) and payload.get("summary"):
        return str(payload["summary"]).strip()
    return ""


def run_pipeline(
    topic: str,
    language: str,
    count: int,
    provider: str,
    model: str,
    temperature: float,
    groq_api_key: str = "",
) -> list[dict[str, Any]]:
    llm = build_llm(
        provider=provider,
        model=model,
        temperature=temperature,
        groq_api_key=groq_api_key,
    )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    names = generate_author_names(llm=llm, topic=topic, count=count)
    if not names:
        raise RuntimeError("The LLM did not return any author names.")

    results: list[dict[str, Any]] = []

    for name in names:
        candidates = wikidata_search_entities(
            session=session,
            name=name,
            language=language,
            limit=5,
        )

        chosen = choose_best_entity(
            llm=llm,
            topic=topic,
            author_name=name,
            candidates=candidates,
        )

        if not chosen:
            results.append({
                "input_name": name,
                "chosen_qid": None,
                "chosen_label": None,
                "summary": "",
                "facts_count": 0,
            })
            continue

        qid = str(chosen.get("id", "")).strip()
        label = str(chosen.get("label", name)).strip()

        facts = wikidata_schema_walk(
            session=session,
            qid=qid,
            language=language,
            limit=50,
        )

        summary = summarize_entity(
            llm=llm,
            entity_label=label,
            qid=qid,
            facts=facts,
            language=language,
        )

        results.append(
            {
                "input_name": name,
                "chosen_qid": qid,
                "chosen_label": label,
                "summary": summary,
                "facts_count": len(facts),
            }
        )

    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangChain pipeline querying Wikidata directly.")
    parser.add_argument(
        "--topic",
        default="well-known science-fiction authors",
        help="Topic used to generate author names and guide ranking.",
    )
    parser.add_argument("--language", default="en", help="Wikidata language code (default: en).")
    parser.add_argument("--count", type=int, default=10, help="How many authors to process.")
    parser.add_argument(
        "--config",
        default="config.ini",
        help="Path to config.ini used for provider defaults.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file loaded before reading API keys. Use empty value to disable.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "groq"],
        default="ollama",
        help="LLM provider for LangChain.",
    )
    parser.add_argument(
        "--model",
        default="",
        help=(
            "Model name. Examples: ollama -> llama3.1:8b, "
            "groq -> llama-3.3-70b-versatile. If omitted, read from config.ini."
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="LLM temperature. If omitted, use config.ini or 0.0.",
    )
    parser.add_argument("--out", default="", help="Optional output JSON file path.")
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
        items = run_pipeline(
            topic=args.topic,
            language=args.language,
            count=args.count,
            provider=args.provider,
            model=model,
            temperature=temperature,
            groq_api_key=defaults.get("GROQ_API_KEY", ""),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(items, ensure_ascii=False, indent=2))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
