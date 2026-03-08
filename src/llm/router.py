"""
llm_translator.py — Semantic Router (Intent Layer)

The LLM acts ONLY as an intent classifier.
It does not reason about permissions or costs — Z3 does that.

In production: OpenAI / Anthropic with Structured Outputs (Pydantic).
In this repository: deterministic mock to connect with the formal engine.
"""

import os
from src.models import LLMIntent, IntentType


def translate_query(query: str) -> LLMIntent:
    """
    Receives the user's query in natural language.
    Uses an LLM (Structured Outputs) to return the validated JSON
    with the semantic intent and search parameters.

    In production, this would use the OpenAI API:
    ---------------------------------------------
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
    ---------------------------------------------

    Or the Anthropic API:
    ---------------------------------------------
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": query}],
    )
    return LLMIntent.model_validate_json(message.content[0].text)
    ---------------------------------------------
    """

    print(f"  [LLM] Classifying intent for: '{query}'")

    # --- Mock: Intent detection by keywords ---
    query_lower = query.lower()

    # Keywords for each module
    blast_keywords = ["blast radius", "financial damage", "maximum cost",
                      "hack", "compromise", "financial", "max damage", "cost"]
    access_keywords = ["can", "access", "delete", "remove", "permission"]

    # Detect intent
    is_blast = any(kw in query_lower for kw in blast_keywords)
    is_access = any(kw in query_lower for kw in access_keywords)

    if is_blast and not is_access:
        intent = IntentType.BLAST_RADIUS
    elif is_access and not is_blast:
        intent = IntentType.ACCESS_VERIFICATION
    elif is_blast:
        # If there is ambiguity, blast radius wins when financial keywords are present
        intent = IntentType.BLAST_RADIUS
    else:
        intent = IntentType.ACCESS_VERIFICATION

    # --- Mock: Parameter extraction based on intent ---
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
