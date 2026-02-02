$ErrorActionPreference = "Stop"

# 1. Install uv if missing
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    pip install uv
}

# 2. Create Virtual Environment
Write-Host "Creating virtual environment in System_Testing/.venv..."
uv venv System_Testing/.venv

# 3. Install Dependencies
Write-Host "Installing dependencies into virtual environment..."
# Install backend requirements
uv pip install -p System_Testing/.venv -r backend/requirements.txt
# Install test dependencies
uv pip install -p System_Testing/.venv pytest pytest-asyncio pytest-mock pytest-cov

Write-Host "Setup complete!"
Write-Host "To run tests, use:"
Write-Host "  . System_Testing\.venv\Scripts\activate"
Write-Host "  pytest"
