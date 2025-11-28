import logging
from typing import Any

from rdflib import URIRef

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.llmgraph_groq import llm_graph_groq

logger = logging.getLogger(__name__)


def WIKIDATA_SCHEMA_TO_SPARQL(utterance: Any, entity: Any, g_schema: Any) -> Any:
    """GGF-style UDF: given an utterance, a main entity and a local schema graph,
    ask an LLM to generate a SPARQL query for the Wikidata endpoint.

    Parameters (from SPARQL):
      - utterance: user question (string or literal)
      - entity: main Wikidata entity IRI (e.g., wd:Q42)
      - g_schema: named graph IRI containing the local schema around the entity

    Returns: a named graph IRI produced by llm_graph_groq, expected to contain
    the generated SPARQL query as literal(s).
    """
    text_utterance = str(utterance)
    main_entity = URIRef(str(entity))

    logger.info("WIKIDATA_SCHEMA_TO_SPARQL: utterance=%s entity=%s schema_graph=%s",
                text_utterance, main_entity, g_schema)

    # Read the schema graph from the shared store and serialize it for the LLM
    named_graph = store.get_context(g_schema)
    logger.info("WIKIDATA_SCHEMA_TO_SPARQL: loaded schema graph with %d triples", len(named_graph))

    # For now, we just serialize the schema graph in Turtle inline for the LLM.
    # This avoids having to GROUP_CONCAT from SPARQL.
    schema_turtle = named_graph.serialize(format="turtle").decode("utf-8") if hasattr(named_graph.serialize(format="turtle"), "decode") else named_graph.serialize(format="turtle")

    prompt = f"""You are an expert on Wikidata and SPARQL.

User question (natural language):
{text_utterance}

Main entity: {main_entity}

You are given a local schema around this entity, expressed in Turtle (RDF):

```turtle
{schema_turtle}
```

Using ONLY this schema and your knowledge of the Wikidata data model, write a SPARQL query for the Wikidata SPARQL endpoint that answers the question.

Constraints:
- The query must start with appropriate PREFIX declarations.
- Use the main entity {main_entity} as the anchor when relevant.
- The query must be a valid SPARQL 1.1 SELECT query.
- Do NOT include any explanation, only the SPARQL query.

Return the result as a JSON-LD document of the form:
{{
  "@context": {{ "cand": "http://example.org/cand#" }},
  "@graph": [
    {{ "@type": "cand:GeneratedQuery", "cand:sparql": "..." }}
  ]
}}
"""

    logger.debug("WIKIDATA_SCHEMA_TO_SPARQL prompt (first 500 chars): %s", prompt[:500])

    # Delegate to the existing Groq JSON-LD helper, which will create a named graph
    g_query = llm_graph_groq(prompt)
    logger.info("WIKIDATA_SCHEMA_TO_SPARQL: produced graph %s", g_query)

    return g_query
