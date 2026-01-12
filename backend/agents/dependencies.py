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
MAX_RECURSION_DEPTH = int(os.getenv("MAX_RECURSION_DEPTH", "3"))