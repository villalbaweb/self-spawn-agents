"""
Rate Limiting and Concurrency Control for LLM Calls.

Provides system-wide rate limiting to prevent API throttling
and implements retry logic with exponential backoff.
"""
import asyncio
import openai
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

from config.settings import MAX_CONCURRENCY

# Global semaphore to limit concurrent LLM calls system-wide
GLOBAL_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENCY)


async def safe_ainvoke(runnable, input_data, config=None):
    """
    Executes a runnable.ainvoke with system-wide concurrency limits and 
    rate-limit retries.
    
    Args:
        runnable: A LangChain runnable (LLM, chain, etc.)
        input_data: Input to pass to the runnable
        config: Optional RunnableConfig with callbacks, etc.
        
    Returns:
        The result of runnable.ainvoke()
        
    Raises:
        openai.RateLimitError: After 6 retry attempts
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
