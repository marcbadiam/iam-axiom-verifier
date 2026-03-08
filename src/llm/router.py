"""
src/llm/router.py

Semantic Router (Intent Layer).
Provider-agnostic router that connects to Gemini or OpenAI (via Structured Outputs),
or falls back to a deterministic mock.
"""

import os
import time
from src.models import LLMIntent, IntentType

# ==========================================
# LLM CONFIGURATION
# ==========================================
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
USE_MOCK = os.getenv("USE_MOCK_LLM", "true").lower() == "true"

def translate_query(query: str) -> LLMIntent:
    """
    Routes the natural language query to the correct mathematical module.
    """
    print(f"  [LLM] Classifying intent for: '{query}'...")

    if USE_MOCK:
        return _call_mock_llm(query)

    if LLM_PROVIDER == "gemini":
        return _call_gemini_llm(query)
    elif LLM_PROVIDER == "openai":
        return _call_openai_llm(query)
    else:
        print(f"  [LLM] ⚠️ Unknown provider '{LLM_PROVIDER}'. Falling back to mock.")
        return _call_mock_llm(query)

def _call_gemini_llm(query: str) -> LLMIntent:
    """Production mode: Uses Gemini Structured Outputs to guarantee the Pydantic schema."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("Please run: pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    print("  [LLM] 🌐 Calling Gemini API (gemini-2.5-flash)...")
    
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a cloud security semantic router. Analyze the user's query "
                "and extract the target IAM role, the AWS action (if any), and "
                "determine if the intent is ACCESS_VERIFICATION or BLAST_RADIUS."
            ),
            response_mime_type="application/json",
            response_schema=LLMIntent,
            temperature=0.0, # Strict deterministic output
        ),
    )
    
    return LLMIntent.model_validate_json(response.text)

def _call_openai_llm(query: str) -> LLMIntent:
    """Production mode: Uses OpenAI Structured Outputs to guarantee the Pydantic schema."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Please run: pip install openai")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in the environment.")

    print("  [LLM] 🌐 Calling OpenAI API (gpt-4o-mini)...")
    
    client = OpenAI(api_key=api_key)
    
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
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