import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.utilities import GoogleSerperAPIWrapper

# Load environment variables
load_dotenv()

# # Initialize LLM (DeepSeek)
# llm = ChatOpenAI(
#     api_key=os.getenv("DEEPSEEK_API_KEY"),
#     base_url="https://api.deepseek.com",
#     model="deepseek-chat", 
#     temperature=0.7 
# )

# Initialize LLM (OpenAI) - Default/Smart Model
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model=os.getenv("OPENAI_MODEL", "gpt-4o"), 
    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    max_retries=3
)

# Initialize LLM (OpenAI) - Fast/Cheap Model
llm_mini = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model=os.getenv("OPENAI_MODEL_MINI", "gpt-4o-mini"), 
    temperature=float(os.getenv("OPENAI_TEMPERATURE_MINI", "0.1")),
    max_retries=3
)

# Initialize Tools
search = GoogleSerperAPIWrapper(k=10) 

# Configuration
# Recommendation: Keep MAX_RECURSION_DEPTH <= 4 to avoid exponential branching (3^depth spawns)
MAX_RECURSION_DEPTH = int(os.getenv("MAX_RECURSION_DEPTH", "3"))

# --- CONFIGURABLE HITL THRESHOLDS ---
# Set these environment variables to test HITL behavior:
TIER1_THRESHOLD = float(os.getenv("HITL_TIER1_THRESHOLD", "0.85")) # Below this triggers self-correction
TIER2_THRESHOLD = float(os.getenv("HITL_TIER2_THRESHOLD", "0.60")) # Below this sets low_confidence_flag
TIER3_THRESHOLD = float(os.getenv("HITL_TIER3_THRESHOLD", "0.35")) # Below this triggers Hard Stop interrupt

# --- RATE LIMIT PROTECTION ---
import asyncio
import openai
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

# Global semaphore to limit concurrent LLM calls system-wide
# Default to 10 concurrent calls if not specified in env
MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "10"))
GLOBAL_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENCY)

async def safe_ainvoke(runnable, input_data, config=None):
    """
    Executes a runnable.ainvoke with system-wide concurrency limits and 
    rate-limit retries.
    """
    # 1. Determine which semaphore to use (config override or global)
    # This allows specific graphs to potentially have stricter limits
    sem = GLOBAL_SEMAPHORE
    if config and "configurable" in config and "semaphore" in config["configurable"]:
        sem = config["configurable"]["semaphore"]
        
    # 2. Define the retry-wrapped execution function
    @retry(
        retry=retry_if_exception_type(openai.RateLimitError),
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        reraise=True
    )
    async def _invoke_with_retry():
        async with sem:
            return await runnable.ainvoke(input_data, config=config)
            
    # 3. Execute
    return await _invoke_with_retry()