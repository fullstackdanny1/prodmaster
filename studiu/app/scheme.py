"""Schemele JSON trimise stratului AI (subsetul suportat: type, properties, required, items,
enum, minItems, maxItems, minLength). Definite într-un singur loc."""

CARDURI = {
    "type": "object",
    "required": ["carduri"],
    "properties": {
        "carduri": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tip", "intrebare", "raspuns"],
                "properties": {
                    "tip": {"type": "string", "enum": ["intrebare", "completare"]},
                    "intrebare": {"type": "string", "minLength": 3},
                    "raspuns": {"type": "string", "minLength": 1},
                    "variante": {"type": "array", "items": {"type": "string"}},
                    "corect": {"type": "integer"},
                    "explicatie": {"type": "string"},
                },
            },
        }
    },
}

CUVINTE_CHEIE = {
    "type": "object",
    "required": ["cuvinte"],
    "properties": {
        "cuvinte": {"type": "array", "minItems": 1, "maxItems": 15, "items": {"type": "string", "minLength": 2}},
    },
}
