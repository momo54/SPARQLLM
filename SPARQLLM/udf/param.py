from __future__ import annotations

import os

from rdflib import Literal
from rdflib.namespace import XSD


def param(name: object, default: object = ""):
    """Return environment variable value with optional default.

    Usage in SPARQL:
      BIND(ggf:PARAM("SLM_AUTHOR", "Pascal Molli") AS ?author)
    """
    key = str(name).strip()
    fallback = str(default)
    value = os.getenv(key)
    if value is None or value == "":
        value = fallback
    return Literal(value, datatype=XSD.string)
