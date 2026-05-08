from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from SPARQLLM.entity_graph_core import METAQA_LABEL_PRED, to_text
from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


CAND = Namespace("http://example.org/cand#")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:local-schema:{prefix}:{digest}")


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


@dataclass
class SchemaSlot:
    hop_count: int
    direction: str
    property_iri: str
    frequency: int = 0
    neighbor_examples: list[str] = field(default_factory=list)
    literal_examples: list[str] = field(default_factory=list)


def _label_for(source: Graph, node: URIRef) -> str:
    rdfs_labels = sorted({str(obj) for obj in source.objects(node, RDFS.label) if str(obj)})
    if rdfs_labels:
        return rdfs_labels[0]
    metaqa_labels = sorted({str(obj) for obj in source.objects(node, METAQA_LABEL_PRED) if str(obj)})
    if metaqa_labels:
        return metaqa_labels[0]
    return ""


def LOCAL_SCHEMA(*args: Any) -> Any:
    """Build a compact local schema around one entity.

    Supported signatures:
      - ggf:LOCAL-SCHEMA(entity_iri, hops=1, direction="both", max_examples=3)
      - ggf:LOCAL-SCHEMA(g_source, entity_iri, hops=1, direction="both", max_examples=3)
    """
    if not 1 <= len(args) <= 5:
        raise ValueError(
            "LOCAL-SCHEMA expects either (entity[, hops[, direction[, max_examples]]]) or "
            "(g_source, entity[, hops[, direction[, max_examples]]])"
        )

    if len(args) >= 2 and existing_graph_uri(args[0]) is not None:
        g_uri, src = resolve_source_graph(args[0])
        center_iri = to_text(args[1])
        hop_limit = max(1, _to_int(args[2], 1)) if len(args) >= 3 else 1
        mode = to_text(args[3]).lower() if len(args) >= 4 else "both"
        example_cap = max(1, _to_int(args[4], 3)) if len(args) >= 5 else 3
    else:
        g_uri, src = resolve_source_graph()
        center_iri = to_text(args[0])
        hop_limit = max(1, _to_int(args[1], 1)) if len(args) >= 2 else 1
        mode = to_text(args[2]).lower() if len(args) >= 3 else "both"
        example_cap = max(1, _to_int(args[3], 3)) if len(args) >= 4 else 3

    center = URIRef(center_iri)
    mode = mode or "both"
    if mode not in {"out", "in", "both"}:
        mode = "both"

    slots: dict[tuple[int, str, str], SchemaSlot] = {}
    seen_depth: dict[URIRef, int] = {center: 0}
    queue: deque[tuple[URIRef, int]] = deque([(center, 0)])

    while queue:
        node, depth = queue.popleft()
        if depth >= hop_limit:
            continue

        if mode in {"out", "both"}:
            outgoing = sorted(
                src.triples((node, None, None)),
                key=lambda triple: (str(triple[1]), str(triple[2])),
            )
            for _, pred, obj in outgoing:
                key = (depth + 1, "out", str(pred))
                slot = slots.setdefault(key, SchemaSlot(depth + 1, "out", str(pred)))
                slot.frequency += 1
                if isinstance(obj, URIRef):
                    if len(slot.neighbor_examples) < example_cap:
                        slot.neighbor_examples.append(str(obj))
                    next_depth = depth + 1
                    prev = seen_depth.get(obj)
                    if prev is None or next_depth < prev:
                        seen_depth[obj] = next_depth
                        queue.append((obj, next_depth))
                else:
                    val = str(obj)
                    if len(slot.literal_examples) < example_cap and val not in slot.literal_examples:
                        slot.literal_examples.append(val)

        if mode in {"in", "both"}:
            incoming = sorted(
                src.triples((None, None, node)),
                key=lambda triple: (str(triple[1]), str(triple[0])),
            )
            for subj, pred, _ in incoming:
                key = (depth + 1, "in", str(pred))
                slot = slots.setdefault(key, SchemaSlot(depth + 1, "in", str(pred)))
                slot.frequency += 1
                if isinstance(subj, URIRef):
                    if len(slot.neighbor_examples) < example_cap:
                        slot.neighbor_examples.append(str(subj))
                    next_depth = depth + 1
                    prev = seen_depth.get(subj)
                    if prev is None or next_depth < prev:
                        seen_depth[subj] = next_depth
                        queue.append((subj, next_depth))

    out_uri = _graph_uri("result", [str(g_uri), center_iri, str(hop_limit), mode, str(example_cap)])
    out = store.get_context(out_uri)
    out.bind("cand", CAND)
    out.bind("rdfs", RDFS)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, CAND.LocalSchema))
    out.add((root, CAND["center"], center))
    out.add((root, CAND["maxHops"], Literal(hop_limit, datatype=XSD.integer)))
    out.add((root, CAND["direction"], Literal(mode)))
    out.add((root, CAND["slotCount"], Literal(len(slots), datatype=XSD.integer)))

    center_label = _label_for(src, center)
    if center_label:
        out.add((root, CAND["centerLabel"], Literal(center_label)))

    ordered_slots = sorted(slots.values(), key=lambda s: (s.hop_count, s.direction, s.property_iri))
    for rank, slot in enumerate(ordered_slots, start=1):
        node = BNode()
        out.add((node, RDF.type, CAND.SchemaSlot))
        out.add((node, CAND["rank"], Literal(rank, datatype=XSD.integer)))
        out.add((node, CAND["hopCount"], Literal(slot.hop_count, datatype=XSD.integer)))
        out.add((node, CAND["direction"], Literal(slot.direction)))
        out.add((node, CAND["property"], URIRef(slot.property_iri)))
        out.add((node, CAND["frequency"], Literal(slot.frequency, datatype=XSD.integer)))
        out.add((root, CAND["slot"], node))

        prop_label = _label_for(src, URIRef(slot.property_iri))
        if prop_label:
            out.add((node, CAND["propertyLabel"], Literal(prop_label)))

        for neighbor_iri in slot.neighbor_examples:
            ex = URIRef(neighbor_iri)
            out.add((node, CAND["exampleNeighbor"], ex))
            neighbor_label = _label_for(src, ex)
            if neighbor_label:
                out.add((ex, RDFS.label, Literal(neighbor_label)))

        for literal_value in slot.literal_examples:
            out.add((node, CAND["exampleLiteral"], Literal(literal_value)))

    return out_uri
