# LangSmith Trace Downloader Guide

This guide explains how to use the `download_trace.py` script to programmatically download trace data from LangSmith for debugging and analysis.

## Overview

The script fetches **all runs** associated with a specific LangSmith Trace ID and saves them as a JSON list to a local file. This is useful for offline inspection of complex agent execution trees.

## Prerequisites

1.  **Environment Variables**: The script requires access to LangSmith. It looks for the following environment variables in a `.env` file in the project root:
    *   `LANGCHAIN_API_KEY`: Your LangSmith API Key.
    *   *Alternative*: `LANGSMITH_API_KEY` (will be used if `LANGCHAIN_API_KEY` is not found).

2.  **Dependencies**: valid python environment with `langsmith` and `python-dotenv` installed.
    *   Run `uv sync` or ensure `backend/requirements.txt` dependencies are installed.

## Usage

Run the script from the project root using `uv run` (or your preferred python execution method):

```powershell
uv run python backend/scripts/download_trace.py <TRACE_ID>
```

### Arguments

*   `<TRACE_ID>`: The unique identifier for the trace you want to download. You can find this in the URL of the LangSmith trace view (e.g., `https://smith.langchain.com/o/.../projects/.../traces/THIS_IS_THE_ID`).

### Example

```powershell
uv run python backend/scripts/download_trace.py 019bafae-7185-7023-9340-0cc21e9f78fe
```

## Output

The script generates a JSON file in the current working directory named:
`trace_<TRACE_ID>.json`

*   **Format**: A JSON Array `[...]` containing run objects.
*   **Content**: Contains full details of every run in the trace tree (inputs, outputs, events, metadata).

## Troubleshooting

*   **Error: LANGCHAIN_API_KEY ... not found**: Ensure you have a `.env` file in the project root and it contains your API key.
*   **Error fetching run**: Verify the Trace ID is correct and you have access to the project containing the trace.
