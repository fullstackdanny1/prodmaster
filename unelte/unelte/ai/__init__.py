"""Stratul AI comun pentru Studiu și Unelte (copiat identic în ambele proiecte).

Dacă modifici pachetul, crește AI_LAYER_VERSION și copiază-l și în celălalt proiect.
"""
AI_LAYER_VERSION = "1.0.0"

from .client import (AIError, Diagnostic, Rezultat, check_model_ref, consum,  # noqa: E402
                     estimeaza_cost, estimeaza_tokeni, info_model, listeaza_modele, load_config,
                     max_chunk_chars, modele_configurate, rezumat_consum, ruleaza, set_application,
                     testeaza)
from .config import ConfigError  # noqa: E402

__all__ = [
    "AI_LAYER_VERSION", "AIError", "ConfigError", "Diagnostic", "Rezultat", "check_model_ref",
    "consum", "estimeaza_cost", "estimeaza_tokeni", "info_model", "listeaza_modele", "load_config",
    "max_chunk_chars", "modele_configurate", "rezumat_consum", "ruleaza", "set_application",
    "testeaza",
]
