import os
import sys
import json
from dotenv import load_dotenv
from langsmith import Client

def setup_env():
    """Load environment variables from .env file."""
    # Look for .env in the project root directory
    # Script is in backend/scripts/download_trace.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    root_dir = os.path.dirname(backend_dir)
    dotenv_path = os.path.join(root_dir, ".env")

    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print(f"Loaded environment from {dotenv_path}")
    else:
        # Fallback to standard locations or existing env vars
        load_dotenv()
        print("Loaded environment from standard locations")

def download_trace(trace_id):
    """Downloads a trace from LangSmith and saves it to a JSON file."""
    try:
        # Ensure API keys are present
        if not os.getenv("LANGCHAIN_API_KEY"):
            # Check for LANGSMITH_API_KEY as fallback
            if os.getenv("LANGSMITH_API_KEY"):
                os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
                print("Using LANGSMITH_API_KEY as LANGCHAIN_API_KEY")
            else:
                print("Error: LANGCHAIN_API_KEY (or LANGSMITH_API_KEY) not found in environment variables.")
                return

        client = Client()
        print(f"Fetching all runs for trace {trace_id}...")
        # list_runs returns an iterator, convert to list
        runs = list(client.list_runs(trace_id=trace_id))
        
        # Create filename
        filename = f"trace_{trace_id}.json"
        
        # Save to file
        with open(filename, "w", encoding='utf-8') as f:
            # Use model_dump() instead of dict() (Pydantic V2)
            json.dump([run.model_dump() for run in runs], f, indent=2, default=str)
            
        print(f"Successfully saved {len(runs)} runs in trace to {filename}")
        
    except Exception as e:
        print(f"Error fetching run: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_trace.py <TRACE_ID>")
        sys.exit(1)
        
    setup_env()
    trace_id_arg = sys.argv[1]
    download_trace(trace_id_arg)
