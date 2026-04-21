"""JSON:API <-> flat dict helpers.

TOCOnline responses follow JSON:API (`data`, `attributes`, `relationships`,
`included`, `meta`). Flattening removes the envelope so LLMs deal with plain
objects like `{id, type, name, email, customer_id}`.
"""

from __future__ import annotations

from typing import Any

_RESERVED = {"id", "type"}


def flatten_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Flatten a single JSON:API resource object."""
    out: dict[str, Any] = {}
    if "id" in resource:
        out["id"] = resource["id"]
    if "type" in resource:
        out["type"] = resource["type"]
    attributes = resource.get("attributes")
    if isinstance(attributes, dict):
        for key, value in attributes.items():
            out[f"attr_{key}" if key in _RESERVED else key] = value
    relationships = resource.get("relationships")
    if isinstance(relationships, dict):
        for rel_name, rel in relationships.items():
            data = rel.get("data") if isinstance(rel, dict) else None
            if data is None:
                out[f"{rel_name}_id"] = None
            elif isinstance(data, list):
                out[f"{rel_name}_ids"] = [
                    item.get("id") for item in data if isinstance(item, dict)
                ]
            elif isinstance(data, dict):
                out[f"{rel_name}_id"] = data.get("id")
                rel_type = data.get("type")
                if rel_type:
                    out[f"{rel_name}_type"] = rel_type
            else:
                out[f"{rel_name}_id"] = None
    return out


def flatten_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a JSON:API response body (single resource or collection)."""
    if not isinstance(payload, dict):
        return {"result": payload}
    data = payload.get("data")
    meta = payload.get("meta")
    if isinstance(data, list):
        result: dict[str, Any] = {"items": [flatten_resource(r) for r in data if isinstance(r, dict)]}
        if meta:
            result["meta"] = meta
        if payload.get("links"):
            result["links"] = payload["links"]
        return result
    if isinstance(data, dict):
        flat = flatten_resource(data)
        if meta:
            flat["_meta"] = meta
        return flat
    return payload


def build_resource_envelope(
    resource_type: str, attributes: dict[str, Any], relationships: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a JSON:API write envelope from flat inputs."""
    resource: dict[str, Any] = {"type": resource_type, "attributes": {k: v for k, v in attributes.items() if v is not None}}
    if relationships:
        rel_out: dict[str, Any] = {}
        for name, ref in relationships.items():
            if ref is None:
                continue
            if isinstance(ref, list):
                rel_out[name] = {"data": [{"type": t, "id": str(i)} for t, i in ref]}
            else:
                ref_type, ref_id = ref
                rel_out[name] = {"data": {"type": ref_type, "id": str(ref_id)}}
        if rel_out:
            resource["relationships"] = rel_out
    return {"data": resource}
