"""
src/llm/router.py

Semantic Router (Intent Layer).
Connects to OpenAI (via Structured Outputs) or falls back to a deterministic mock.
"""

import os
import time
from src.models import LLMIntent, IntentType

# ==========================================
# LLM CONFIGURATION
# ==========================================
# Allows the user to choose which environment variable to read (Defaults to OPENAI_API_KEY)
API_KEY_ENV_NAME = os.getenv("LLM_API_KEY_VAR_NAME", "OPENAI_API_KEY")
API_KEY = os.getenv(API_KEY_ENV_NAME)

# Safety kill-switch: Allows forcing the Mock mode via environment variable
USE_MOCK = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

def translate_query(query: str) -> LLMIntent:
    """
    Routes the natural language query to the correct mathematical module.
    """
    print(f"  [LLM] Classifying intent for: '{query}'...")

    # If the user wants to use the real API and the key is configured
    if not USE_MOCK and API_KEY:
        return _call_real_llm(query)
    else:
        return _call_mock_llm(query)

def _call_real_llm(query: str) -> LLMIntent:
    """Production mode: Uses OpenAI Structured Outputs to guarantee the Pydantic schema."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please run: pip install openai")

    print(f"  [LLM] 🌐 Calling OpenAI API (using env var: {API_KEY_ENV_NAME})...")
    
    client = OpenAI(api_key=API_KEY)
    
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini", # Using the mini model for speed and cost-efficiency
        messages=[
            {
                "role": "system", 
                "content": (
                    "You are a cloud security semantic router. Analyze the user's query "
                    "and extract the target IAM role, the AWS action (if any), and "
                    "determine if the intent is ACCESS_VERIFICATION or BLAST_RADIUS."
                )
            },
            {"role": "user", "content": query}
        ],
        response_format=LLMIntent,
    )
    
    return completion.choices[0].message.parsed

def _call_mock_llm(query: str) -> LLMIntent:
    """Fallback mode: Deterministic keyword routing for testing without costs."""
    print("  [LLM] 🧪 Using local deterministic mock (No API costs).")
    time.sleep(0.8) # Simulate network delay

    query_lower = query.lower()
    blast_keywords = ["blast radius", "financial damage", "maximum cost", "hack", "cost"]
    
    is_blast = any(kw in query_lower for kw in blast_keywords)

    if is_blast:
        return LLMIntent(
            intent=IntentType.BLAST_RADIUS,
            target_role="DataEng-Team",
            target_action=None,
            target_resource=None,
            target_regions=["us-east-1"],
        )
    else:
        return LLMIntent(
            intent=IntentType.ACCESS_VERIFICATION,
            target_role="DevTeam-Junior",
            target_action="rds:DeleteDBInstance",
            target_resource="*",
            target_regions=["us-east-1"],
        )