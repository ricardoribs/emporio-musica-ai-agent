import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "store.db"
POLICIES_PATH = DATA_DIR / "políticas_da_loja.pdf"

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"


def get_settings() -> Settings:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não encontrada. Configure a variável no arquivo .env.")

    return Settings(
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
