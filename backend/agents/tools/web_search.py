from langchain_core.tools import tool
from agents.dependencies import search

@tool
def web_search(query: str) -> str:
    """
    Performs a web search using Google Serper to find information on the internet.
    Use this tool when you need to answer questions about current events, specific technical details, or find external documentation.
    
    Args:
        query (str): The search query to execute.
        
    Returns:
        str: A summary of the search results.
    """
    try:
        if not query:
            return "Please provide a valid search query."
            
        print(f"🔎 Searching the web for: {query}")
        return search.run(query)
    except Exception as e:
        return f"Error performing web search: {str(e)}"
