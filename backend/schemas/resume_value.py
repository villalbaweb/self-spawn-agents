from pydantic import BaseModel, Field
from typing import Optional, Literal, Any, Dict

class ResumeValue(BaseModel):
    """
    Standardized structure for Human-In-The-Loop resume values.
    
    This ensures type safety when handling user inputs after an interrupt.
    """
    action: Literal["proceed", "abort", "retry", "manual_fix"] = Field(
        ..., 
        description="The action to take: 'proceed' (ignore warning), 'abort' (stop), 'retry' (re-run), or 'manual_fix' (inject output)."
    )
    output: Optional[str] = Field(
        None, 
        description="The manual output to inject if action is 'manual_fix'."
    )
    reasoning: Optional[str] = Field(
        None, 
        description="Optional user reasoning for the decision, useful for audit logs."
    )
    
    @classmethod
    def proceed_resume(cls, reasoning: str = "User override"):
        """Convenience factory for proceeding."""
        return cls(action="proceed", reasoning=reasoning)
        
    @classmethod
    def abort_resume(cls, reasoning: str = "User aborted"):
        """Convenience factory for aborting."""
        return cls(action="abort", reasoning=reasoning)
        
    @classmethod
    def retry_resume(cls, reasoning: str = "User requested retry"):
        """Convenience factory for retrying."""
        return cls(action="retry", reasoning=reasoning)
        
    @classmethod
    def manual_fix_resume(cls, output: str, reasoning: str = "User provided manual fix"):
        """Convenience factory for manual fix."""
        return cls(action="manual_fix", output=output, reasoning=reasoning)

    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary for LangGraph state updates."""
        return self.model_dump(exclude_none=True)
