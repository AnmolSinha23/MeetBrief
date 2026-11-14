#!/usr/bin/env python3
"""Generates or regenerates data/samples/sample_briefing.json."""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import MeetingInput, MeetingType, EntityType
from app.pipeline import run_pipeline

async def generate_sample(mock: bool = False):
    load_dotenv()
    if mock:
        os.environ["MOCK_MODE"] = "true"

    meeting_time = datetime.now(timezone.utc) + timedelta(days=1)
    inp = MeetingInput(
        entity="Stripe",
        entity_type=EntityType.company,
        meeting_time=meeting_time,
        timezone="UTC",
        meeting_type=MeetingType.investor,
        hint="Financial infrastructure and payments platform",
        user_context="Evaluating high-scale payment processing and autonomous agent commerce primitives.",
    )

    print(f"Generating sample briefing for {inp.entity} (MOCK_MODE={os.getenv('MOCK_MODE', 'false')})...")
    briefing = await run_pipeline(inp)

    out_dir = Path("data/samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "sample_briefing.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(briefing.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    print(f"Sample briefing successfully written to {out_file}")
    print(f"Status: {briefing.status}")
    print(f"Developments: {len(briefing.draft.developments)}")
    print(f"Sources cited: {len(briefing.sources)}")

def main():
    parser = argparse.ArgumentParser(description="Generate sample briefing JSON")
    parser.add_argument("--mock", action="store_true", help="Force mock offline fixtures")
    args = parser.parse_args()
    asyncio.run(generate_sample(mock=args.mock))

if __name__ == "__main__":
    main()
