# System Testing

This directory contains the centralized testing suite for the project, managed by `uv`.

## Setup

Run the setup script to create the virtual environment and install dependencies:

```powershell
.\System_Testing\setup_tests.ps1
```

## Running Tests

Activate the environment and run pytest:

```powershell
. System_Testing\.venv\Scripts\activate
pytest
```
