from langchain_core.tools import tool
from e2b_code_interpreter import AsyncSandbox
import os

E2B_API_KEY = os.getenv("E2B_API_KEY")

@tool
async def python_repl(code: str) -> str:
    """
    Execute Python code in a secure cloud sandbox.
    Use this tool when you need to run calculations, data processing, or generate outputs.
    
    Args:
        code (str): The Python code to execute. Must print results to stdout.
        
    Returns:
        str: The stdout output from the code execution, or an error message.
    """
    if not E2B_API_KEY:
        return "Error: E2B_API_KEY not configured. Cannot execute Python code."
    
    print(f"🐍 Executing Python code in E2B sandbox...")
    
    try:
        async with await AsyncSandbox.create(api_key=E2B_API_KEY) as sandbox:
            execution = await sandbox.run_code(code)
            
            # Get stdout from logs
            stdout = execution.logs.stdout if execution.logs else ""
            stderr = execution.logs.stderr if execution.logs else ""
            
            if stderr:
                print(f"⚠️ Python stderr: {stderr[:200]}")
                
            if execution.error:
                return f"Execution Error: {execution.error}"
                
            output = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
            
            print(f"✅ Python execution complete. Output length: {len(output)}")
            return output if output else "Code executed successfully (no output)"
            
    except Exception as e:
        return f"E2B Sandbox Error: {str(e)}"
