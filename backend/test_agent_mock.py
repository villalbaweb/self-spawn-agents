import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import os

# Set dummy env vars
os.environ["OPENAI_API_KEY"] = "dummy"
os.environ["OPENAI_MODEL"] = "gpt-4o"
os.environ["OPENAI_TEMPERATURE"] = "0.7"
os.environ["SERPER_API_KEY"] = "dummy"

async def run_test():
    print("Starting Graph Test...")
    
    # Setup Mocks
    mock_llm_instance = MagicMock()
    
    # Mock with_structured_output
    mock_structured_llm = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured_llm
    
    # Return values for invoke
    mock_llm_instance.invoke.side_effect = [
        MagicMock(content='[{"address": "123 Mock St", "neighborhood": "Mock Neighborhood", "price": "400000", "estimated_market_price": "500000", "justification": "Underpriced by 20%", "opportunity_score": 9, "link": "http://example.com/1", "imageUrl": "http://example.com/img.jpg"}]'), # Search Agent Result Extraction
        MagicMock(content='[{"address": "123 Mock St", "neighborhood": "Mock Neighborhood", "price": "400000", "estimated_market_price": "500000", "justification": "Underpriced by 20%", "opportunity_score": 9, "link": "http://example.com/1", "imageUrl": "http://example.com/img.jpg"}]'), # Analyst
    ]
    
    # Return value for structured output invoke
    from agents.compiler_agent import PropertyReportList, PropertyReport, Contact
    mock_report = PropertyReport(
        id="prop_001",
        address="123 Mock St",
        neighborhood="Mock Neighborhood",
        price="400000",
        estimated_market_price="500000",
        details="Great deal",
        justification="Underpriced by 20%",
        contact=Contact(email="test@realestate.com", phone="12345678"),
        link="http://example.com/1",
        imageUrl="http://example.com/img.jpg",
        opportunity_score="9"
    )
    mock_structured_llm.invoke.return_value = PropertyReportList(reports=[mock_report])
    
    mock_search_instance = MagicMock()
    mock_search_instance.results.return_value = {'organic': [{'title': 'Mock', 'link': 'http://example.com/1', 'snippet': 'Mock'}]}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><h1>123 Mock St</h1><p>Beautiful house for sale. 200m2.</p></body></html>"
    
    # Patch everything together
    with patch('agents.dependencies.llm', new=mock_llm_instance), \
         patch('agents.dependencies.search', new=mock_search_instance), \
         patch('httpx.AsyncClient') as MockClient:
        
        mock_client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response

        # Import agent INSIDE the patch
        from agent import app_graph

        initial_state = {
            "query": "Jardines del Bosque", 
            "search_results": [], 
            "property_candidates": [],
            "detailed_content": [],
            "analyzed_properties": [], 
            "opportunities": [], 
            "final_results": []
        }
        
        try:
            result = await app_graph.ainvoke(initial_state)
            print("Graph finished successfully.")
            final_res = result.get("final_results", [])
            print("Final Results count:", len(final_res))
            
            assert len(final_res) > 0, "Should have results"
            assert final_res[0]['address'] == "123 Mock St"
            print("TEST PASSED: Data flowed through all nodes.")
            
        except Exception as e:
            print(f"TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            exit(1)

if __name__ == "__main__":
    asyncio.run(run_test())
