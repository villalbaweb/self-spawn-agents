
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

class MockLLM:
    """
    Helper class to create mock LLM objects (like ChatOpenAI) 
    that return deterministic responses.
    """
    
    @staticmethod
    def create_mock_llm(response_text: str = "Mocked Response"):
        """
        Returns an AsyncMock that mimics a LangChain ChatModel.
        Both ainvoke and invoke return an AIMessage with the given text.
        """
        mock_llm = AsyncMock()
        
        # Create standard response
        message = AIMessage(content=response_text)
        
        # Mock async call
        mock_llm.ainvoke.return_value = message
        
        # Mock sync call
        mock_llm.invoke.return_value = message
        
        return mock_llm

def mock_tool_response(tool_name: str, return_value: str) -> AsyncMock:
    """
    Creates a mock for a tool that returns a specific string value.
    """
    mock_tool = AsyncMock()
    mock_tool.name = tool_name
    mock_tool.ainvoke.return_value = return_value
    mock_tool.invoke.return_value = return_value
    return mock_tool
