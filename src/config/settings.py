import json
from pathlib import Path
from datetime import timezone, timedelta, date
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_BASE  = PROJECT_ROOT / "output"
IST          = timezone(timedelta(hours=5, minutes=30))


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def output_dir(run_date: str) -> Path:
    return OUTPUT_BASE / run_date


def load_manifest(run_date: str) -> dict:
    path = output_dir(run_date) / "run_manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"run_manifest.json not found for {run_date}. Run L0 first:\n"
            f"  python -m src.pipeline.L0_manifest.runner --date {run_date}"
        )
    return json.loads(path.read_text())
