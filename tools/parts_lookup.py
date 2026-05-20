"""Automotive parts lookup tool — calls hermes-auto-parts-api to find part numbers."""

import json
import os
import httpx
from tools.registry import registry, tool_error

PARTS_LOOKUP_SCHEMA = {
    "name": "parts_lookup",
    "description": (
        "Look up an automotive part number given a description of the part and a VIN. "
        "Returns the part number, name, category, and vehicle info from the parts database. "
        "When the database has no match, returns source='not_found' so you can fall back to web search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "part_description": {
                "type": "string",
                "description": "Human-readable description of the part (e.g. 'front brake caliper, single piston')",
            },
            "vin": {
                "type": "string",
                "description": "Vehicle Identification Number (17 characters)",
            },
        },
        "required": ["part_description", "vin"],
    },
}


def parts_lookup(part_description: str, vin: str) -> str:
    if not part_description or not part_description.strip():
        return tool_error("part_description is required")
    if not vin or not vin.strip():
        return tool_error("vin is required")

    api_url = os.environ.get("PARTS_API_URL", "").rstrip("/")
    if not api_url:
        return tool_error("PARTS_API_URL is not configured")

    try:
        resp = httpx.post(
            f"{api_url}/lookup",
            json={"part_description": part_description.strip(), "vin": vin.strip()},
            timeout=15.0,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except httpx.HTTPStatusError as exc:
        return tool_error(f"Parts API returned {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        return tool_error(f"Parts API unreachable: {exc}")


def _check_parts_api() -> bool:
    return bool(os.environ.get("PARTS_API_URL", "").strip())


registry.register(
    name="parts_lookup",
    toolset="automotive",
    schema=PARTS_LOOKUP_SCHEMA,
    handler=lambda args, **kw: parts_lookup(
        args.get("part_description", ""),
        args.get("vin", ""),
    ),
    check_fn=_check_parts_api,
    emoji="🔧",
)
