"""Validator JSON Schema minimal (fără dependențe) și extragerea JSON-ului din răspunsuri.

Subsetul suportat: type, properties, required, items, enum, minItems, maxItems, minLength.
"""
from __future__ import annotations

import json
import re

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


class SchemaError(ValueError):
    pass


def _type_ok(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(t)
    return py is not None and isinstance(value, py)


def errors(value, schema: dict, path: str = "$") -> list[str]:
    out: list[str] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in types):
            return [f"{path}: se aștepta tipul {'/'.join(types)}, am primit {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: valoarea {value!r} nu e printre {schema['enum']!r}")
    if isinstance(value, str) and "minLength" in schema and len(value.strip()) < schema["minLength"]:
        out.append(f"{path}: textul are mai puțin de {schema['minLength']} caractere")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path}: lista are {len(value)} elemente, minimum {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path}: lista are {len(value)} elemente, maximum {schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                out += errors(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{path}: lipsește câmpul obligatoriu «{k}»")
        for k, sub in (schema.get("properties") or {}).items():
            if k in value:
                out += errors(value[k], sub, f"{path}.{k}")
    return out


def validate(value, schema: dict) -> None:
    errs = errors(value, schema)
    if errs:
        raise SchemaError("; ".join(errs[:8]))


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.S)


def extract_json(text: str):
    """Scoate primul obiect sau prima listă JSON din text (blocuri de cod, text în jur)."""
    text = (text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise SchemaError("Răspunsul nu conține JSON.")
    start = min(starts)
    decoder = json.JSONDecoder()
    try:
        value, _end = decoder.raw_decode(text[start:])
        return value
    except json.JSONDecodeError as e:
        raise SchemaError(f"JSON invalid: {e.msg} (poziția {e.pos}).") from e


def describe(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=1)
