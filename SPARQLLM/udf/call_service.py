from __future__ import annotations

import logging
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from rdflib import Literal
from rdflib.namespace import XSD

from SPARQLLM.config import ConfigSingleton


logger = logging.getLogger(__name__)


_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_]\w*)\}")


def _expand_env_placeholders(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.getenv(name, "")

    return _ENV_PLACEHOLDER.sub(repl, text)


def _redact_url(url: str) -> str:
    try:
        split = urlsplit(url)
        query = parse_qsl(split.query, keep_blank_values=True)
        masked = []
        for k, v in query:
            if k.lower() in {"api_key", "key", "token", "access_token"}:
                masked.append((k, "***"))
            else:
                masked.append((k, v))
        return urlunsplit((split.scheme, split.netloc, split.path, urlencode(masked), split.fragment))
    except Exception:
        return url


def call_service(url: object):
    """Fetch JSON from a dynamic URL and return it as an xsd:string literal.

    Intended usage from SPARQL:
      BIND(ggf:CALL-SERVICE(?url) AS ?jsonString)
    """
    raw_url = _expand_env_placeholders(str(url).strip())
    if not raw_url:
        return Literal("[]", datatype=XSD.string)

    config = ConfigSingleton()
    timeout = int(config.config["Requests"].get("SLM-TIMEOUT", 120))

    headers = {
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
        "User-Agent": "SPARQLLM/1.0",
    }

    try:
        response = requests.get(raw_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return Literal(response.text, datatype=XSD.string)
    except Exception as exc:
        logger.warning("CALL-SERVICE failed for %s: %s", _redact_url(raw_url), exc)
        return Literal("[]", datatype=XSD.string)
