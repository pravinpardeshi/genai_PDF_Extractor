from __future__ import annotations

import json
from typing import Any, List
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

PROMPT_TEMPLATE = """
You are a data cleanup assistant. Given a JSON array of tables extracted from a PDF,
standardize headers (lowercase, alphanumeric with underscores), remove spurious empty columns,
and fix rows that are off by one by shifting cells if obvious. Return only valid JSON with the same shape:
[{{"page": int, "table_index": int, "headers": [str], "rows": [[any]]}}] with no commentary.

Input JSON:
{input_json}
"""


async def clean_tables_with_ollama(tables: List[dict]) -> List[dict]:
    try:
        input_json = json.dumps(tables, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(input_json=input_json)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama /api/generate returns { response: "..." }
            text = data.get("response", "").strip()
            # Attempt to parse JSON content
            cleaned = json.loads(text)
            if isinstance(cleaned, list):
                return cleaned
            return tables
    except Exception:
        # Fail gracefully if LLM is not available or returns bad JSON
        return tables
