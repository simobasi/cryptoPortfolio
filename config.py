import json
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
SECRETS_FILE = PROJECT_ROOT / "API_KEYS.env"

load_dotenv(SECRETS_FILE)

WALLET_ENV_KEYS = {
    "ethereum": {
        "ledger": "ETH_LEDGER_ADDRESS",
    },
    "solana": {
        "ledger": "SOL_LEDGER_ADDRESS",
        "phantom": "SOL_PHANTOM_ADDRESS",
    },
}


def load_config() -> dict:
    with CONFIG_FILE.open("r") as f:
        return json.load(f)


def get_wallet_address(chain: str, name: str) -> str:
    env_key = WALLET_ENV_KEYS[chain][name]
    value = os.getenv(env_key)
    if not value:
        raise RuntimeError(f"Config mancante in API_KEYS.env: {env_key}")
    return value


def get_data_file(name: str) -> Path:
    return PROJECT_ROOT / load_config()["files"][name]
