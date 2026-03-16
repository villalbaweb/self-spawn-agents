from typing import Optional
from agentguard_sdk.client import GovernanceException

def get_governance_exception(e: Exception) -> Optional[GovernanceException]:
    """
    Recursively inspects an exception and its causes to find a GovernanceException.
    This is necessary because LLM libraries (like openai) often wrap underlying
    exceptions into their own connection or API errors.
    """
    if isinstance(e, GovernanceException):
        return e
    
    # Check the cause (explicitly chained via 'from')
    if hasattr(e, "__cause__") and e.__cause__:
        res = get_governance_exception(e.__cause__)
        if res:
            return res
            
    # Check the context (implicitly caught)
    if hasattr(e, "__context__") and e.__context__:
        res = get_governance_exception(e.__context__)
        if res:
            return res
            
    return None

def is_governance_block(e: Exception) -> bool:
    """
    Returns True if the exception or any of its causes is a GovernanceException.
    """
    return get_governance_exception(e) is not None
