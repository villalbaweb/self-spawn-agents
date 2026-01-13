from langchain_core.tools import tool
from agents.dependencies import search
import re

@tool
def web_search(query: str) -> str:
    """
    Performs a web search using Google Serper to find information on the internet.
    Use this tool when you need to answer questions about current events, specific technical details, or find external documentation.
    
    Args:
        query (str): The search query to execute.
        
    Returns:
        str: A summary of the search results with metadata about missing terms.
    """
    try:
        if not query:
            return "Please provide a valid search query."
            
        print(f"🔎 Searching the web for: {query}")
        results = search.run(query)
        
        # Extract "Missing:" metadata patterns from search results
        missing_terms = re.findall(r'Missing:\s*(\w+)', results)
        
        if missing_terms:
            missing_block = f"\n\n[SEARCH_METADATA]\nMissing terms not found in results: {', '.join(set(missing_terms))}\nConsider refining your search if these terms are critical.\n[/SEARCH_METADATA]"
            print(f"⚠️ Search flagged missing terms: {set(missing_terms)}")
            return results + missing_block
        
        return results
    except Exception as e:
        return f"Error performing web search: {str(e)}"
