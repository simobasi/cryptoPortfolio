import os
import sys
from collections import defaultdict
from pathlib import Path

import krakenex
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from funzioniUtili import normalizza_tickername_kraken


load_dotenv(PROJECT_ROOT / "API_KEYS.env")


def _get_client():
    return krakenex.API(
        key=os.getenv("KRAKEN_API_KEY"),
        secret=os.getenv("KRAKEN_API_SECRET"),
    )


def get_balances_kraken(show_zero: bool = False, normalize: bool = True) -> dict:
    response = _get_client().query_private("Balance")
    errors = response.get("error") or []

    if errors:
        raise RuntimeError(f"Errore Kraken: {errors}")

    balances = defaultdict(float)

    for asset, amount in response.get("result", {}).items():
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            continue

        if not show_zero and amount <= 0:
            continue

        ticker = normalizza_tickername_kraken(asset) if normalize else asset
        balances[ticker] += amount

    return {k: v for k, v in sorted(balances.items()) if show_zero or v != 0.0}


def stampa_portafoglio_kraken(balances: dict) -> None:
    print("\nPORTAFOGLIO KRAKEN")
    print("------------------")

    for asset, amount in balances.items():
        print(f"{asset}: {amount}")


def main() -> None:
    try:
        balances = get_balances_kraken()
    except Exception as exc:
        print("Errore:", exc)
        return

    stampa_portafoglio_kraken(balances)


if __name__ == "__main__":
    main()
