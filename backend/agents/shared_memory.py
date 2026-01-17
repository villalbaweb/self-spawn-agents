from langgraph.checkpoint.memory import MemorySaver

# Shared memory instance for both outer and inner graphs
# This ensures state persistence across node re-executions
memory = MemorySaver()
