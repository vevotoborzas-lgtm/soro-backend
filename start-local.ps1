param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    $python = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $python) {
        $python = (Get-Command py -ErrorAction SilentlyContinue)
    }
    if (-not $python) {
        throw "Python is not available on PATH. Install Python 3.11+ or create .venv manually."
    }
    & $python.Source -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -r requirements.txt

$env:PORT = [string]$Port
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
