# -*- coding: utf-8 -*-
"""FAISS MCP provider for SPARQLLM

Provides two tools:
- faiss.index_file: index a TTL file (schema:text) into a FAISS index and optionally persist it
- faiss.search_index: search a persisted FAISS index for a query string

Return contract: a minimal JSON-LD dict with media_type and jsonld payload.

This provider is intended to be called from the MCP tool layer, e.g.
  slm:SLM-MCP-TOOL("faiss","faiss.index_file", slm:SLM-OBJ("file","./events.nt.ttl","index_path","./events.index","persist",true))
and
  slm:SLM-MCP-TOOL("faiss","faiss.search_index", slm:SLM-OBJ("index_path","./events.index","query","music in Berlin","k",3))
"""
from __future__ import annotations
import os
import json
import logging
import tempfile
import hashlib
from typing import List, Dict, Any

from rdflib import Graph, Namespace, URIRef

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    # Optional: provider can fall back to deterministic local embeddings.
    SentenceTransformer = None

try:
    import faiss
except Exception:
    faiss = None

try:
    import numpy as np
except Exception:
    np = None

logger = logging.getLogger("faiss_provider")
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class FaissProvider:
    # Historique du code: certaines données utilisent https://schema.org/ (avec slash final),
    # le code original utilisait http://schema.org/. On supporte maintenant les deux.
    SCHEMA = Namespace("http://schema.org/")
    SCHEMA_HTTPS = Namespace("https://schema.org/")
    INDEX_EXT = ".index"
    JSONLD_CONTEXT_KEY = "@context"
    JSONLD_TYPE_KEY = "@type"
    JSONLD_GRAPH_KEY = "@graph"
    JSONLD_MEDIA_TYPE = "application/ld+json"

    def __init__(self):
        if faiss is None or np is None:
            logger.warning("faiss or numpy not available; FAISS provider calls will fail until installed")
        elif SentenceTransformer is None:
            logger.info("sentence-transformers unavailable; using deterministic local embeddings fallback")

    def _fallback_embed(self, text: str, dimensions: int = 384) -> Any:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        state = np.frombuffer(seed, dtype=np.uint32).copy()
        values = np.empty(dimensions, dtype=np.float32)
        for i in range(dimensions):
            x = state[i % len(state)]
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= (x >> 17)
            x ^= (x << 5) & 0xFFFFFFFF
            state[i % len(state)] = x
            values[i] = ((x % 10000) / 5000.0) - 1.0
        return values

    def _encode_texts(self, texts: List[str], model: str, normalize: bool) -> Any:
        if SentenceTransformer is not None:
            model_obj = SentenceTransformer(model)
            emb = model_obj.encode(texts, normalize_embeddings=normalize)
            return np.array(emb, dtype='float32')

        emb = np.array([self._fallback_embed(t) for t in texts], dtype='float32')
        if normalize:
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            emb = emb / norms
        return emb

    def _extract_texts(self, ttl_path: str) -> List[Dict[str, Any]]:
        g = Graph()
        g.parse(ttl_path, format="turtle")
        entries = []
        text_predicates = [
            self.SCHEMA.text,
            self.SCHEMA_HTTPS.text,
            self.SCHEMA.description if hasattr(self.SCHEMA, 'description') else URIRef("http://schema.org/description"),
            self.SCHEMA_HTTPS.description if hasattr(self.SCHEMA_HTTPS, 'description') else URIRef("https://schema.org/description"),
        ]
        name_predicates = [
            self.SCHEMA.name if hasattr(self.SCHEMA, 'name') else URIRef("http://schema.org/name"),
            self.SCHEMA_HTTPS.name if hasattr(self.SCHEMA_HTTPS, 'name') else URIRef("https://schema.org/name"),
        ]

        # On collecte tous les sujets candidats ayant AU MOINS un de ces prédicats texte
        candidate_subjects = set()
        for tp in text_predicates:
            for s in g.subjects(predicate=tp):
                candidate_subjects.add(s)
        # Si aucun prédicat 'text' trouvé, fallback sur 'description' ou 'name'
        if not candidate_subjects:
            for npred in name_predicates:
                for s in g.subjects(predicate=npred):
                    candidate_subjects.add(s)

        for s in candidate_subjects:
            text_val = None
            # Cherche priorité: text -> description -> name (premier trouvé)
            for tp in text_predicates:
                tv = g.value(subject=s, predicate=tp)
                if tv:
                    text_val = tv
                    break
            if not text_val:
                for npred in name_predicates:
                    tv = g.value(subject=s, predicate=npred)
                    if tv:
                        text_val = tv
                        break
            if not text_val:
                continue
            props = {str(p): str(o) for p, o in g.predicate_objects(subject=s)}
            entries.append({"uri": str(s), "text": str(text_val), "props": props})

        if not entries:
            logger.info("No schema:text (http/https) nor description/name literals found in %s" % ttl_path)
            # Optionnel: échantillon des prédicats disponibles pour debug
            sample_preds = sorted({str(p) for _, p, _ in list(g)[:500]})[:25]
            logger.debug("Sample predicates: %s" % sample_preds)
        else:
            logger.info("Extracted %d text entries from %s" % (len(entries), ttl_path))
        return entries

    def tool_index_file(
        self,
        file: str,
        model: str = "all-MiniLM-L6-v2",
        index_path: str | None = None,
        persist: bool = False,
        normalize: bool = True,
        index_type: str = "flat",
        metric: str = "ip",
        hnsw_m: int = 32,
        hnsw_ef_construction: int = 200,
        hnsw_ef_search: int = 50,
    ) -> dict:
        """Index TTL file into FAISS.

        Args:
            file: path to ttl file
            model: sentence-transformers model name
            index_path: optional path to write faiss index and metadata (without extension)
            persist: whether to persist index and metadata to disk
            normalize: normalize embeddings (recommended for IndexFlatIP)
            index_type: 'flat' or 'hnsw'
            metric: 'ip', 'l2', or 'cosine' (cosine mapped to normalized IP)
            hnsw_m: HNSW graph degree (M)
            hnsw_ef_construction: HNSW efConstruction parameter
            hnsw_ef_search: initial efSearch parameter stored in metadata (can be overridden at query time)

        Returns:
            dict: JSON-like contract with media_type and jsonld
        """
        logger.info("Indexing file %s (model=%s, index_type=%s, metric=%s)" % (file, model, index_type, metric))
        if faiss is None or np is None:
            return {"error": "missing_dependency", "message": "Install faiss and numpy"}
        if not os.path.exists(file):
            return {"error": "file_not_found", "file": file}

        entries = self._extract_texts(file)
        texts = [e["text"] for e in entries]
        if not texts:
            return {"error": "no_texts_found", "file": file}

        emb = self._encode_texts(texts, model=model, normalize=normalize)
        dim = emb.shape[1]

        index_type_norm = index_type.lower()
        metric_norm = metric.lower()

        # Choose FAISS index
        # Flat IP (original behavior) OR HNSW variants. For cosine, we normalize embeddings and treat as IP or L2 depending.
        # We use index_factory for HNSW to allow IP vs L2 easily.
        if index_type_norm == 'flat':
            if metric_norm in ('ip', 'cosine'):
                index = faiss.IndexFlatIP(dim)
                effective_metric = 'ip'
            else:
                index = faiss.IndexFlatL2(dim)
                effective_metric = 'l2'
        elif index_type_norm == 'hnsw':
            # Build string for factory: e.g. HNSW32,IP or HNSW32
            hnsw_descr = f"HNSW{hnsw_m}"
            if metric_norm in ('ip', 'cosine'):
                hnsw_descr += ",IP"
                effective_metric = 'ip'
            else:
                effective_metric = 'l2'
            try:
                index = faiss.index_factory(dim, hnsw_descr)
            except Exception as e:
                return {"error": "hnsw_build_failed", "message": str(e), "descriptor": hnsw_descr}
            # Tune HNSW hyper-parameters if available
            if hasattr(index, 'hnsw'):
                try:
                    index.hnsw.efConstruction = int(hnsw_ef_construction)
                    index.hnsw.efSearch = int(hnsw_ef_search)
                except Exception:
                    pass
        else:
            return {"error": "unsupported_index_type", "index_type": index_type}

        index.add(emb)

        meta = {
            "entries": [{"uri": e["uri"], "props": e["props"]} for e in entries],
            "model": model,
            "count": len(entries),
            "index_type": index_type_norm,
            "metric": effective_metric,
            "normalize": bool(normalize),
        }
        if index_type_norm == 'hnsw':
            meta.update({
                "hnsw_M": int(hnsw_m),
                "hnsw_ef_construction": int(hnsw_ef_construction),
                "hnsw_ef_search": int(hnsw_ef_search)
            })

        if persist:
            if not index_path:
                # create temp base path
                base = tempfile.NamedTemporaryFile(delete=False).name
                index_path = base
            idx_file = index_path if index_path.endswith(self.INDEX_EXT) else index_path + self.INDEX_EXT
            meta_file = index_path + '.meta.json'
            # ensure directory exists
            d = os.path.dirname(os.path.abspath(idx_file))
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
            faiss.write_index(index, idx_file)
            with open(meta_file, 'w', encoding='utf-8') as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)
            logger.info("Persisted index to %s and metadata to %s" % (idx_file, meta_file))
            jsonld = {self.JSONLD_CONTEXT_KEY: {"schema": str(self.SCHEMA)}, self.JSONLD_TYPE_KEY: "FaissIndex", "index_path": idx_file, "meta_path": meta_file, "count": len(entries), "index_type": index_type_norm, "metric": meta.get('metric')}
            return {"media_type": self.JSONLD_MEDIA_TYPE, "jsonld": jsonld, "graph_anchor": idx_file}

        # In-memory return: not persisted, but provide metadata in payload
        jsonld = {self.JSONLD_CONTEXT_KEY: {"schema": str(self.SCHEMA)}, self.JSONLD_TYPE_KEY: "FaissIndex", "index_in_memory": True, "count": len(entries), "index_type": index_type_norm, "metric": meta.get('metric')}
        # Attach small sample metadata (uris)
        jsonld["uris"] = [e["uri"] for e in entries]
        return {"media_type": self.JSONLD_MEDIA_TYPE, "jsonld": jsonld, "graph_anchor": file}

    def tool_search_index(
        self,
        index_path: str | None,
        query: str,
        k: int = 5,
        model: str = "all-MiniLM-L6-v2",
        file: str | None = None,
        index_type: str | None = None,
        metric: str | None = None,
        hnsw_ef_search: int | None = None,
    ) -> dict:
        """Search a persisted FAISS index.

        Args:
            index_path: base path used when persisting (without extension) or full .index path
            query: query string
            k: number of results
            model: embedding model

        Returns:
            dict: JSON-LD with matches
        """
        logger.info("Searching index %s for query '%s'" % (index_path, query))
        if faiss is None or np is None:
            return {"error": "missing_dependency", "message": "Install faiss and numpy"}
        # allow passing a ttl 'file' to create the index on demand
        if not index_path and file:
            # default index base is the file path without extension + '.faiss'
            index_path = os.path.splitext(file)[0] + '.faiss'

        if not index_path:
            return {"error": "missing_index_path", "message": "Provide index_path or file to build"}

        idx_file = index_path if index_path.endswith(self.INDEX_EXT) else index_path + self.INDEX_EXT
        meta_file = index_path + '.meta.json'

        # If index missing but a TTL file is provided, build and persist it first
        if (not os.path.exists(idx_file) or not os.path.exists(meta_file)) and file:
            logger.info("Index not found, creating index from file %s" % file)
            res = self.tool_index_file(
                file=file,
                model=model,
                index_path=index_path,
                persist=True,
                index_type=index_type or 'flat',
                metric=metric or 'ip'
            )
            if res.get('error'):
                return {"error": "index_build_failed", "cause": res}

        if not os.path.exists(idx_file) or not os.path.exists(meta_file):
            return {"error": "index_not_found", "idx_file": idx_file, "meta_file": meta_file}

        try:
            index = faiss.read_index(idx_file)
        except Exception as e:
            logger.error("Failed to read index: %s", e)
            return {"error": "read_index_failed", "message": str(e)}

        with open(meta_file, 'r', encoding='utf-8') as fh:
            meta = json.load(fh)

        # If metadata indicates embeddings were normalized originally, we do the same now.
        normalize_flag = bool(meta.get('normalize', True))
        q_emb = self._encode_texts([query], model=model, normalize=normalize_flag)
        D, I = index.search(q_emb, k)

        # If HNSW and user provided an override for efSearch, attempt to set then re-run search
        if hnsw_ef_search and hasattr(index, 'hnsw'):
            try:
                index.hnsw.efSearch = int(hnsw_ef_search)
                D, I = index.search(q_emb, k)
            except Exception:
                pass

        matches = []
        metric_type = meta.get('metric', 'ip')
        for raw_score, idx in zip(D[0].tolist(), I[0].tolist()):
            if idx < 0 or idx >= len(meta.get('entries', [])):
                continue
            entry = meta['entries'][idx]
            # Convert distance to a score if L2 (smaller distance => better). We keep consistency: higher score is better.
            if metric_type == 'l2':
                score = -float(raw_score)
            else:
                score = float(raw_score)
            matches.append({"uri": entry.get('uri'), "score": score, "props": entry.get('props')})

        # Build RDF-ready JSON-LD with @graph: one main result node linking to match nodes
        try:
            h = hashlib.sha256(json.dumps({"query": query, "matches": matches}, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
        except Exception:
            h = "tmp"

        result_id = f"urn:faiss:search:{h}"
        graph_obj = {self.JSONLD_CONTEXT_KEY: {"schema": str(self.SCHEMA), "ex": "http://example.org/"}, self.JSONLD_GRAPH_KEY: []}

        # main result node
        main_node = {"@id": result_id, self.JSONLD_TYPE_KEY: "FaissSearchResult"}
        main_node[str(self.SCHEMA.query) if hasattr(self.SCHEMA, 'query') else "query"] = query

        match_nodes = []
        for m in matches:
            m_id = m.get('uri') or f"urn:faiss:match:{hashlib.sha256(json.dumps(m, ensure_ascii=False).encode('utf-8')).hexdigest()[:12]}"
            node = {"@id": m_id}
            if 'score' in m:
                node["http://example.org/score"] = m.get('score')
            props = m.get('props') or {}
            rdf_type = props.pop("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", None)
            if rdf_type:
                node[self.JSONLD_TYPE_KEY] = rdf_type
            for p, v in props.items():
                node[p] = v

            match_nodes.append(node)

            # link from main node to match using schema:hasPart
            key = str(self.SCHEMA.hasPart)
            main_node.setdefault(key, [])
            main_node[key].append({"@id": m_id})

        graph_obj[self.JSONLD_GRAPH_KEY].append(main_node)
        graph_obj[self.JSONLD_GRAPH_KEY].extend(match_nodes)

        return {"media_type": self.JSONLD_MEDIA_TYPE, "jsonld": graph_obj, "graph_anchor": idx_file}

    # registry
    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": "faiss.index_file", "description": "Index a TTL file into FAISS (flat or HNSW)", "inputs": ["file","model","index_path","persist","normalize","index_type","metric","hnsw_M","hnsw_ef_construction","hnsw_ef_search"]},
            {"name": "faiss.search_index", "description": "Search a persisted FAISS index (or provide file to auto-build)", "inputs": ["index_path","file","query","k","model","index_type","metric","hnsw_ef_search"]},
        ]

    def call(self, tool_name: str, args: dict) -> dict:
        if tool_name == "faiss.index_file":
            return self.tool_index_file(
                file=args.get('file'),
                model=args.get('model','all-MiniLM-L6-v2'),
                index_path=args.get('index_path'),
                persist=bool(args.get('persist', False)),
                normalize=bool(args.get('normalize', True)),
                index_type=args.get('index_type','flat'),
                metric=args.get('metric','ip'),
                hnsw_m=int(args.get('hnsw_M',32)),
                hnsw_ef_construction=int(args.get('hnsw_ef_construction',200)),
                hnsw_ef_search=int(args.get('hnsw_ef_search',50)),
            )
        if tool_name == "faiss.search_index":
            return self.tool_search_index(
                index_path=args.get('index_path'),
                query=args.get('query',''),
                k=int(args.get('k',5)),
                model=args.get('model','all-MiniLM-L6-v2'),
                file=args.get('file'),
                index_type=args.get('index_type'),
                metric=args.get('metric'),
                hnsw_ef_search=args.get('hnsw_ef_search')
            )
        return {"error": "unknown_tool", "tool": tool_name}


# singleton factory
_provider_singleton: FaissProvider | None = None

def get_provider() -> FaissProvider:
    global _provider_singleton
    if _provider_singleton is None:
        _provider_singleton = FaissProvider()
    return _provider_singleton
