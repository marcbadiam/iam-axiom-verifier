"""
llm_translator.py — Enrutador Semántico (Capa de Intención)

El LLM actúa ÚNICAMENTE como clasificador de intención.
No razona sobre permisos ni costes — eso lo hace Z3.

En producción: OpenAI / Anthropic con Structured Outputs (Pydantic).
En este repositorio: mock determinista para conectar con el motor formal.
"""

import os
from src.models import LLMIntent, IntentType


def translate_query(query: str) -> LLMIntent:
    """
    Recibe la consulta del usuario en lenguaje natural.
    Utiliza un LLM (Structured Outputs) para devolver el JSON validado
    con la intención semántica y los parámetros de la búsqueda.

    En producción, esto usaría la API de OpenAI:
    ─────────────────────────────────────────────
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    completion = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ],
        response_format=LLMIntent,
    )
    return completion.choices[0].message.parsed
    ─────────────────────────────────────────────

    O la API de Anthropic:
    ─────────────────────────────────────────────
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": query}],
    )
    return LLMIntent.model_validate_json(message.content[0].text)
    ─────────────────────────────────────────────
    """

    print(f"  [LLM] Clasificando intención para: '{query}'")

    # ── Mock: Detección de intención por palabras clave ──────────
    query_lower = query.lower()

    # Palabras clave para cada módulo
    blast_keywords = ["radio de explosión", "blast radius", "daño financiero",
                      "coste máximo", "hackean", "compromet", "financiero",
                      "max damage", "cost"]
    access_keywords = ["pueden", "puede", "acceso", "borrar", "eliminar",
                       "delete", "access", "permiso", "permission"]

    # Detectar intención
    is_blast = any(kw in query_lower for kw in blast_keywords)
    is_access = any(kw in query_lower for kw in access_keywords)

    if is_blast and not is_access:
        intent = IntentType.BLAST_RADIUS
    elif is_access and not is_blast:
        intent = IntentType.ACCESS_VERIFICATION
    elif is_blast:
        # Si hay ambigüedad, blast radius gana cuando hay keywords financieros
        intent = IntentType.BLAST_RADIUS
    else:
        intent = IntentType.ACCESS_VERIFICATION

    # ── Mock: Extracción de parámetros según intención ───────────
    if intent == IntentType.ACCESS_VERIFICATION:
        return LLMIntent(
            intent=IntentType.ACCESS_VERIFICATION,
            target_role="DevTeam-Junior",
            target_action="rds:DeleteDBInstance",
            target_resource="*",
            target_regions=["us-east-1"],
        )
    else:
        return LLMIntent(
            intent=IntentType.BLAST_RADIUS,
            target_role="DataEng-Team",
            target_action=None,
            target_resource=None,
            target_regions=["us-east-1"],
        )
