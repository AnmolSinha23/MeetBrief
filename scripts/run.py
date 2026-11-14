#!/usr/bin/env python3
"""MeetBrief Run Script

Loads environment, configures mock mode if requested, and launches the FastAPI server.
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Start MeetBrief application server")
    parser.add_argument("--mock", action="store_true", help="Force MOCK_MODE=true (offline fixtures, no API keys)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    args = parser.parse_args()

    # Load .env if present
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)

    if args.mock:
        os.environ["MOCK_MODE"] = "true"

    mock_status = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")

    print("=" * 60)
    print(" MeetBrief - Pre-Meeting Briefing Agent")
    print(f" URL:       http://{args.host}:{args.port}")
    print(f" Mode:      {'MOCK_MODE (Offline / Fixtures)' if mock_status else 'LIVE (Tavily + Bifrost)'}")
    print("=" * 60)

    try:
        import uvicorn
        uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
    except ImportError:
        print("Error: uvicorn is not installed. Please run: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
