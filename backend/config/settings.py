"""
Application settings and environment configuration.

Centralizes all environment variable loading and threshold definitions.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- RECURSION LIMITS ---
# Recommendation: Keep MAX_RECURSION_DEPTH <= 4 to avoid exponential branching (3^depth spawns)
MAX_RECURSION_DEPTH = int(os.getenv("MAX_RECURSION_DEPTH", "3"))

# --- CONFIGURABLE HITL THRESHOLDS ---
# Set these environment variables to test HITL behavior:
TIER1_THRESHOLD = float(os.getenv("HITL_TIER1_THRESHOLD", "0.85"))  # Below this triggers self-correction
TIER2_THRESHOLD = float(os.getenv("HITL_TIER2_THRESHOLD", "0.60"))  # Below this sets low_confidence_flag
TIER3_THRESHOLD = float(os.getenv("HITL_TIER3_THRESHOLD", "0.35"))  # Below this triggers Hard Stop interrupt

# --- RATE LIMIT PROTECTION ---
MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "10"))

# --- PERSISTENCE ---
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")

# --- INTERRUPT TIMEOUT ---
# Maximum time (in seconds) an interrupt can remain pending before auto-cleanup
INTERRUPT_TIMEOUT_SECONDS = int(os.getenv("INTERRUPT_TIMEOUT_SECONDS", "300"))  # 5 minutes default

# --- API KEYS (accessed via os.getenv where needed) ---
# These are read directly where needed to avoid exposing secrets
# OPENAI_API_KEY, DEEPSEEK_API_KEY, SERPER_API_KEY, E2B_API_KEY
