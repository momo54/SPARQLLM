#!/usr/bin/env python3
"""Run MetaQA TOG-style evaluation against a remote SPARQL endpoint.

Goal:
- Reproduce the high-level behavior of queries/bench/metaqa_eval_2hop_tog.sparql
  without SPARQLLM UDFs.
- Measure SPARQL server transfer and call count.

Outputs:
- CSV with columns similar to the SPARQL query output.
- JSON metrics with call counts and bytes transferred.

Example:
  set -a && source .env && set +a && \
  venv/bin/python scripts/eval_metaqa_tog_remote.py \
      --endpoint http://localhost:9999/sparql \
      --qa-ttl data/metaqa/MetaQA/qa_2hop.ttl \
      --out-csv tmp/metaqa_eval_2hop_tog_remote.csv \
      --out-metrics tmp/metaqa_eval_2hop_tog_remote.metrics.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from rdflib import Graph

LABEL_PRED = "http://metaqa.org/schema/label"


def _slug(iri: str) -> str:
    return iri.rsplit("/", 1)[-1].lower()


def _extract_anchor(question: str) -> str:
    m = re.search(r"\[([^\]]+)\]", question)
    return m.group(1).strip() if m else ""


def _normalize_pipe_list(s: str) -> list[str]:
    if not s:
        return []
    parts = [p.strip().lower() for p in re.split(r"\s*\|\s*", s.strip())]
    return [p for p in parts if p]


def _safe_json_object(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group())
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _relation_hints(question: str) -> set[str]:
    q = question.lower()
    mapping = {
        "written_by": ["written", "screenwriter", "wrote", "writer"],
        "directed_by": ["directed", "director"],
        "starred_actors": ["actor", "actors", "starred", "co-star", "acted"],
        "in_language": ["language", "languages", "spoken"],
        "release_year": ["year", "years", "release", "released", "date"],
        "has_genre": ["genre", "genres", "type", "types"],
    }
    out: set[str] = set()
    for rel, kws in mapping.items():
        if any(k in q for k in kws):
            out.add(rel)
    return out


@dataclass
class HttpMetrics:
    calls: int = 0
    upload_bytes: int = 0
    download_bytes: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "upload_bytes": self.upload_bytes,
            "download_bytes": self.download_bytes,
        }


class SparqlMeterClient:
    def __init__(self, endpoint: str, timeout: int = 30):
        self.endpoint = endpoint
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/sparql-results+json",
                "User-Agent": "SPARQLLM/remote-metaqa-tog-eval",
            }
        )
        self.metrics = HttpMetrics()

    def select(self, query: str) -> list[dict[str, str]]:
        resp = self.session.post(
            self.endpoint,
            data={"query": query},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        self._record(resp)
        payload = resp.json()
        out: list[dict[str, str]] = []
        for row in payload.get("results", {}).get("bindings", []):
            out_row: dict[str, str] = {}
            for k, v in row.items():
                out_row[k] = str(v.get("value", ""))
            out.append(out_row)
        return out

    def _record(self, response: requests.Response) -> None:
        req = response.request
        upload = len((req.url or "").encode("utf-8"))
        if req.body:
            body = req.body if isinstance(req.body, (bytes, bytearray)) else str(req.body).encode("utf-8")
            upload += len(body)
        download = len(response.content or b"")

        self.metrics.calls += 1
        self.metrics.upload_bytes += upload
        self.metrics.download_bytes += download


class GroqClient:
    def __init__(self, model: str, api_key: str):
        from groq import Groq

        self.model = model
        self.client = Groq(api_key=api_key, max_retries=0)
        self.calls = 0

    def prompt(self, content: str, max_tokens: int = 512) -> str:
        self.calls += 1
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()


def load_questions(qa_ttl: Path, limit: int) -> list[dict[str, str]]:
    g = Graph()
    g.parse(str(qa_ttl), format="ttl")

    q = """
    PREFIX mqqa: <http://metaqa.org/qa#>
    SELECT ?qid ?questionText (GROUP_CONCAT(DISTINCT ?ga; separator=" | ") AS ?goldAnswers)
    WHERE {
      ?quri a mqqa:Question ;
            mqqa:id ?qid ;
            mqqa:text ?questionText ;
            mqqa:goldAnswer ?ga .
    }
    GROUP BY ?qid ?questionText
    ORDER BY ?qid
    """
    rows: list[dict[str, str]] = []
    for r in g.query(q):
        rows.append(
            {
                "qid": str(r.qid),
                "questionText": str(r.questionText),
                "goldAnswers": str(r.goldAnswers),
            }
        )
    return rows[:limit]


def resolve_anchor(client: SparqlMeterClient, anchor_label: str) -> tuple[str, str]:
    if not anchor_label:
        return "", ""
    esc = anchor_label.replace('"', '\\"')
    query = f"""
    SELECT ?s ?lbl WHERE {{
      ?s <{LABEL_PRED}> ?lbl .
      FILTER(LCASE(STR(?lbl)) = LCASE("{esc}"))
    }}
    LIMIT 1
    """
    rows = client.select(query)
    if not rows:
        return "", anchor_label
    return rows[0].get("s", ""), rows[0].get("lbl", anchor_label)


def expand_neighbors(client: SparqlMeterClient, entity_iri: str, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    out_query = f"""
    SELECT ?neighbor ?p ?lbl WHERE {{
      <{entity_iri}> ?p ?neighbor .
      FILTER(isIRI(?neighbor))
      OPTIONAL {{ ?neighbor <{LABEL_PRED}> ?lbl }}
    }}
    """
    in_query = f"""
    SELECT ?neighbor ?p ?lbl WHERE {{
      ?neighbor ?p <{entity_iri}> .
      FILTER(isIRI(?neighbor))
      OPTIONAL {{ ?neighbor <{LABEL_PRED}> ?lbl }}
    }}
    """

    for direction, rows in (("out", client.select(out_query)), ("in", client.select(in_query))):
        for r in rows:
            ent = r.get("neighbor", "")
            prop = r.get("p", "")
            if not ent or not prop:
                continue
            key = (ent, prop, direction)
            if key in seen:
                continue
            seen.add(key)
            label = r.get("lbl", "") or ent.rsplit("/", 1)[-1]
            out.append({"entity": ent, "label": label, "prop": prop, "direction": direction})
            if len(out) >= int(limit):
                return out
    return out


def collect_relevant_facts(
    client: SparqlMeterClient,
    entity_iri: str,
    question: str,
    max_per_relation: int = 3,
    max_total: int = 12,
) -> list[str]:
    hints = _relation_hints(question) | {
        "in_language",
        "has_genre",
        "release_year",
        "starred_actors",
        "directed_by",
        "written_by",
    }
    facts: list[str] = []
    per_rel_count: dict[tuple[str, str], int] = {}
    for e in expand_neighbors(client, entity_iri, 200):
        direction = e["direction"]
        slug = _slug(e["prop"])
        if slug not in hints:
            continue
        key = (direction, slug)
        if per_rel_count.get(key, 0) >= max_per_relation:
            continue
        facts.append(f"{direction}:{slug}={e['label']}")
        per_rel_count[key] = per_rel_count.get(key, 0) + 1
        if len(facts) >= max_total:
            return facts
    return facts


def llm_prune_relations(
    llm: GroqClient,
    question: str,
    entity_label: str,
    relations: list[tuple[str, str]],
    top_k: int,
    path_so_far: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    if not relations:
        return []
    if len(relations) <= top_k:
        return relations

    rel_lines = "\n".join(f"{i}. [{d}] {slug}" for i, (d, slug) in enumerate(relations, 1))
    if path_so_far:
        path_str = " -> ".join(f"{lbl} --{d}:{slug}-->" for lbl, d, slug in path_so_far) + f" {entity_label}"
    else:
        path_str = entity_label

    prompt = (
        "You are guiding a knowledge graph traversal to answer a question.\n"
        f'Question: "{question}"\n\n'
        f"Traversal so far: {path_str}\n"
        f'Current entity: "{entity_label}"\n\n'
        "Available relations (out=entity->target, in=source->entity):\n"
        f"{rel_lines}\n\n"
        f"Select up to {top_k} relation numbers (comma-separated) most likely to lead "
        "toward the answer, given the traversal context above. "
        "Output only the numbers, e.g.: 2,5,7"
    )
    raw = llm.prompt(prompt, max_tokens=64)
    idxs = [int(x) for x in re.findall(r"\d+", raw)]
    out = [relations[i - 1] for i in idxs if 1 <= i <= len(relations)]
    if out:
        return out[:top_k]

    # Fallback heuristic
    hints = _relation_hints(question)
    scored = [(1 if slug in hints else 0, d, slug) for d, slug in relations]
    scored.sort(key=lambda x: -x[0])
    return [(d, s) for _, d, s in scored[:top_k]]


def llm_score_candidates(question: str, candidates: list[dict[str, Any]], llm: GroqClient) -> dict[str, float]:
    if not candidates:
        return {}
    numbered = "\n".join(
        f"{i}. Candidate: {c.get('label','')} - {c.get('entity','')}\n"
        f"   Step from: {c.get('from_label','?')} --{c.get('via_property','?')} ({c.get('via_direction','?')})--> {c.get('label','?')}\n"
        f"   Local context: {c.get('cbd_summary','')}"
        for i, c in enumerate(candidates, 1)
    )
    prompt = (
        "You are scoring beam-search candidates by PROGRESS toward answering a question.\n"
        "The candidate does not need to be the final answer itself.\n"
        "Score whether moving from the parent node to this candidate is a useful intermediate step.\n"
        "Each candidate includes traversal edge and local RDF context.\n"
        f'Question: "{question}"\n\n'
        f"Candidates:\n{numbered}\n\n"
        "Scoring rubric:\n"
        "- 1.0: strong progress (clearly moves toward answer type/constraints)\n"
        "- 0.7: moderate progress (plausibly useful intermediate node)\n"
        "- 0.3: weak progress (loosely related, unlikely to help)\n"
        "- 0.0: no progress or distractor\n\n"
        "Important: prefer candidates whose relation/direction and context align with the question intent "
        "(e.g., release year, genre, language, actor, director).\n"
        "Return a single JSON object mapping each entity IRI to a score in [0.0, 1.0]. "
        "Output only the JSON object, no explanation."
    )
    raw = llm.prompt(prompt, max_tokens=1024)
    obj = _safe_json_object(raw)
    out: dict[str, float] = {}
    for k, v in obj.items():
        try:
            out[str(k)] = float(v)
        except Exception:
            continue
    return out


def llm_stop_check(question: str, beam: list[dict[str, Any]], llm: GroqClient) -> bool:
    if not beam:
        return False
    lines = "\n".join(
        f"- {b.get('label','?')} (via {b.get('via_direction','?')}:{_slug(str(b.get('via_property','?')))})"
        for b in beam[:20]
    )
    prompt = (
        "You are answering a multi-hop question by traversing a knowledge graph.\n"
        f'Question: "{question}"\n\n'
        "Current candidate entities on the search frontier:\n"
        f"{lines}\n\n"
        "Can you now answer the question using one or more of these candidates?\n"
        'Respond with ONLY a JSON object: {"can_answer": true/false, "answer": "...or empty"}'
    )
    raw = llm.prompt(prompt, max_tokens=128)
    obj = _safe_json_object(raw)
    return bool(obj.get("can_answer", False))


def llm_final_answer(question: str, candidates: list[dict[str, Any]], llm: GroqClient) -> tuple[str, str]:
    labels = [c.get("label", "") for c in candidates if c.get("label")]
    allowed = " | ".join(labels)
    evidence = "\n".join(
        f"- {c.get('label','')} :: {'; '.join(c.get('relevant_facts', [])[:8]) or '(no facts)'}"
        for c in candidates
    )
    prompt = (
        "Answer the following question using ONLY the candidates listed below.\n"
        "Do NOT invent or paraphrase entities. If none applies, return 'NONE'.\n\n"
        f"Question: {question}\n"
        f"Candidates: {allowed}\n\n"
        f"Candidates with relevant facts:\n{evidence}\n\n"
        "Return ONLY this JSON-LD object (no extra text):\n"
        "{\n"
        "  \"@context\": \"https://schema.org/\",\n"
        "  \"@type\": \"Answer\",\n"
        "  \"text\": \"one concise sentence\",\n"
        "  \"name\": \"one candidate from the list, or NONE\"\n"
        "}\n"
    )
    raw = llm.prompt(prompt, max_tokens=512)
    obj = _safe_json_object(raw)
    selected = str(obj.get("name", "NONE") or "NONE")
    text = str(obj.get("text", "NONE") or "NONE")

    allowed_map = {x.lower(): x for x in labels}
    if selected.lower() in allowed_map:
        selected = allowed_map[selected.lower()]
    elif selected.strip().upper() == "NONE":
        selected = "NONE"
    else:
        selected = "NONE"

    return selected, text


def llm_judge_answer(
    question: str,
    gold_answers: str,
    selected_candidate: str,
    final_answer_text: str,
    llm: GroqClient,
) -> str:
    """LLM-as-a-judge to evaluate correctness with strict rules (matching ToG LOCAL)."""
    prompt = (
        "You are evaluating QA correctness.\n"
        "Decide if prediction is CORRECT with respect to the gold answers.\n"
        "Accept synonyms/case variants, but do not accept different entities.\n"
        "Strict rules:\n"
        "1) If Predicted candidate name is NONE and Gold answers is not NONE => name must be wrong.\n"
        "2) If Predicted candidate name is not in Gold answers, then name is wrong even if answer text is plausible.\n"
        "3) Use answer text only as supporting evidence, never to override rules 1-2.\n"
        "4) Return correct only for exact/near-exact entity match to one gold answer.\n\n"
        f"Question: {question}\n"
        f"Gold answers (pipe-separated): {gold_answers}\n"
        f"Predicted candidate name: {selected_candidate}\n"
        f"Predicted answer text: {final_answer_text}\n\n"
        "Return ONLY this JSON-LD object (no extra text):\n"
        "{\n"
        "  \"@context\": \"https://schema.org/\",\n"
        "  \"@type\": \"Answer\",\n"
        "  \"name\": \"correct or wrong\",\n"
        "  \"text\": \"one short reason\"\n"
        "}\n"
    )
    raw = llm.prompt(prompt, max_tokens=256)
    obj = _safe_json_object(raw)
    judge_label = str(obj.get("name", "") or "").strip().lower()
    if judge_label in ("correct", "wrong"):
        return judge_label
    return "judge_error"


def build_path(node: dict[str, Any]) -> list[tuple[str, str, str]]:
    steps: list[tuple[str, str, str]] = []
    cur = node
    while cur is not None:
        parent = cur.get("parent_ref")
        if parent is None:
            break
        d = cur.get("via_direction") or "out"
        prop = str(cur.get("via_property") or "")
        steps.append((parent.get("label", "?"), d, _slug(prop) if prop else "?"))
        cur = parent
    steps.reverse()
    return steps


def remote_build_cbd(client: SparqlMeterClient, entity_iri: str) -> dict[str, Any]:
    """Build Concise Bounded Description via SPARQL."""
    esc = entity_iri.replace('"', '\\"')
    query = f"""
    SELECT ?p ?direction ?o ?o_lbl WHERE {{
      {{
        BIND("out" AS ?direction)
        <{entity_iri}> ?p ?o .
        FILTER(isIRI(?o))
        OPTIONAL {{ ?o <{LABEL_PRED}> ?o_lbl }}
      }}
      UNION
      {{
        BIND("in" AS ?direction)
        ?o ?p <{entity_iri}> .
        FILTER(isIRI(?o))
        OPTIONAL {{ ?o <{LABEL_PRED}> ?o_lbl }}
      }}
    }}
    LIMIT 100
    """
    rows = client.select(query)
    outgoing = []
    incoming = []
    for r in rows:
        direction = r.get("direction", "out")
        prop = r.get("p", "")
        target = r.get("o", "")
        target_lbl = r.get("o_lbl", "") or target.rsplit("/", 1)[-1]
        prop_slug = _slug(prop)
        if direction == "out":
            outgoing.append({"property": prop_slug, "target": target_lbl})
        else:
            incoming.append({"property": prop_slug, "source": target_lbl})
    return {"outgoing": outgoing, "incoming": incoming}


def format_cbd(cbd: dict[str, Any], label: str = "?") -> str:
    """Format CBD to concise text summary."""
    parts = [label]
    out = cbd.get("outgoing", [])
    if out:
        out_strs = [f"{item['property']}=[{item['target']}]" for item in out[:5]]
        parts.append("out:" + ",".join(out_strs))
    inc = cbd.get("incoming", [])
    if inc:
        inc_strs = [f"{item['property']}=[{item['source']}]" for item in inc[:5]]
        parts.append("in:" + ",".join(inc_strs))
    return " | ".join(parts) if parts else "no context"


def run_tog_question(
    client: SparqlMeterClient,
    llm: GroqClient,
    question: str,
    gold_answers: str,
    max_hops: int,
    beam_width: int,
    expand_k: int,
    top_k_r: int,
) -> dict[str, Any]:
    """Faithful ToG implementation with all steps via SPARQL."""
    anchor = _extract_anchor(question)
    anchor_iri, anchor_label = resolve_anchor(client, anchor)

    if not anchor_iri:
        return {
            "selectedCandidate": "NONE",
            "finalAnswerText": "NONE",
            "correct": "wrong",
            "beam_size": 0,
        }

    beam: list[dict[str, Any]] = [
        {
            "entity": anchor_iri,
            "label": anchor_label,
            "score": 1.0,
            "depth": 0,
            "parent_ref": None,
            "from_label": "",
            "via_property": None,
            "via_direction": None,
            "relevant_facts": collect_relevant_facts(client, anchor_iri, question),
        }
    ]

    # ── Think-on-Graph main loop: 4 steps per hop ────────────────────────────
    for hop in range(1, max_hops + 1):
        # ── (a) Relation pruning: enumerate relations, LLM prunes ────────────
        selected_rels_per_entity: dict[str, list[tuple[str, str]]] = {}
        for parent in beam:
            parent_iri = parent.get("entity", "")
            exps = expand_neighbors(client, parent_iri, expand_k)
            rels: list[tuple[str, str]] = []
            seen = set()
            for exp in exps:
                sig = (exp.get("direction", "out"), _slug(exp.get("prop", "")))
                if sig not in seen:
                    seen.add(sig)
                    rels.append(sig)
            pruned = llm_prune_relations(
                llm,
                question,
                parent.get("label", parent_iri),
                rels,
                top_k_r,
                build_path(parent),
            )
            selected_rels_per_entity[parent_iri] = pruned

        # ── (b) Entity expansion along selected relations ────────────────────
        candidates: dict[str, dict[str, Any]] = {}
        for parent in beam:
            parent_iri = parent.get("entity", "")
            wanted = set(selected_rels_per_entity.get(parent_iri, []))
            if not wanted:
                continue
            exps = expand_neighbors(client, parent_iri, expand_k)
            for exp in exps:
                ent = exp.get("entity", "")
                if not ent or ent == anchor_iri or ent in candidates:
                    continue
                sig = (exp.get("direction", "out"), _slug(exp.get("prop", "")))
                if sig not in wanted:
                    continue
                facts = collect_relevant_facts(client, ent, question)
                candidates[ent] = {
                    "entity": ent,
                    "label": exp.get("label", ""),
                    "depth": int(parent.get("depth", 0)) + 1,
                    "parent_ref": parent,
                    "from_label": parent.get("label", ""),
                    "via_property": exp.get("prop", ""),
                    "via_direction": exp.get("direction", "out"),
                    "relevant_facts": facts,
                }

        if not candidates:
            break

        # ── (c) Entity pruning: build CBD, LLM scores ────────────────────────
        cand_list = list(candidates.values())
        for c in cand_list:
            cbd = remote_build_cbd(client, c["entity"])
            facts_txt = "; ".join(c.get("relevant_facts", [])[:8]) if c.get("relevant_facts") else "(no facts)"
            cbd_txt = format_cbd(cbd, c.get("label", "?"))
            c["cbd_summary"] = f"{cbd_txt} | relevant_facts: {facts_txt}"

        scores = llm_score_candidates(question, cand_list, llm)
        scored = []
        for c in cand_list:
            s = float(scores.get(c["entity"], 0.0))
            if s > 0.0:
                c["score"] = s
                scored.append(c)

        if not scored:
            break

        scored.sort(key=lambda x: x["score"], reverse=True)
        beam = scored[:beam_width]

        # ── (d) Stopping criterion: LLM checks if can answer ─────────────────
        if llm_stop_check(question, beam, llm):
            break

    # ── Generate final answer ────────────────────────────────────────────────
    beam_final = sorted(beam, key=lambda x: float(x.get("score", 0.0)), reverse=True)[:20]
    selected_candidate, final_answer_text = llm_final_answer(question, beam_final, llm)

    # ── Judge the answer with LLM (same strict rules as LOCAL) ──────────────
    correct = llm_judge_answer(question, gold_answers, selected_candidate, final_answer_text, llm)

    return {
        "selectedCandidate": selected_candidate,
        "finalAnswerText": final_answer_text,
        "correct": correct,
        "beam_size": len(beam_final),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate MetaQA with TOG-like pipeline on a remote SPARQL endpoint")
    p.add_argument("--endpoint", required=True, help="SPARQL endpoint URL hosting MetaQA KG")
    p.add_argument("--qa-ttl", default="data/metaqa/MetaQA/qa_2hop.ttl", help="Local QA TTL path")
    p.add_argument("--limit", type=int, default=10, help="Number of questions to evaluate")
    p.add_argument("--out-csv", default="tmp/metaqa_eval_2hop_tog_remote.csv")
    p.add_argument("--out-metrics", default="tmp/metaqa_eval_2hop_tog_remote.metrics.json")
    p.add_argument("--model", default="llama-3.3-70b-versatile")
    p.add_argument("--max-hops", type=int, default=2)
    p.add_argument("--beam-width", type=int, default=10)
    p.add_argument("--expand-k", type=int, default=50)
    p.add_argument("--top-k-r", type=int, default=5)
    p.add_argument("--timeout", type=int, default=30)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required")

    questions = load_questions(Path(args.qa_ttl), args.limit)
    client = SparqlMeterClient(args.endpoint, timeout=args.timeout)
    llm = GroqClient(model=args.model, api_key=api_key)

    rows: list[dict[str, Any]] = []
    for q in questions:
        result = run_tog_question(
            client=client,
            llm=llm,
            question=q["questionText"],
            gold_answers=q["goldAnswers"],
            max_hops=args.max_hops,
            beam_width=args.beam_width,
            expand_k=args.expand_k,
            top_k_r=args.top_k_r,
        )
        rows.append(
            {
                "qid": q["qid"],
                "questionText": q["questionText"],
                "goldAnswers": q["goldAnswers"],
                "selectedCandidate": result["selectedCandidate"],
                "finalAnswerText": result["finalAnswerText"],
                "correct": result["correct"],
                "beamSize": result["beam_size"],
            }
        )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "qid",
                "questionText",
                "goldAnswers",
                "selectedCandidate",
                "finalAnswerText",
                "correct",
                "beamSize",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "endpoint": args.endpoint,
        "questions": len(rows),
        "correct_count": sum(1 for r in rows if r["correct"] == "correct"),
        "sparql": client.metrics.as_dict(),
        "llm_call_count": llm.calls,
        "params": {
            "max_hops": args.max_hops,
            "beam_width": args.beam_width,
            "expand_k": args.expand_k,
            "top_k_r": args.top_k_r,
            "model": args.model,
        },
    }

    out_metrics = Path(args.out_metrics)
    out_metrics.parent.mkdir(parents=True, exist_ok=True)
    out_metrics.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"CSV written: {out_csv}")
    print(f"Metrics written: {out_metrics}")


if __name__ == "__main__":
    main()
