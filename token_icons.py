import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from matplotlib import pyplot as plt
from matplotlib.patches import Circle

from config import PROJECT_ROOT, get_data_file


TOKEN_ICON_DIR = PROJECT_ROOT / "assets" / "tokens"
CMC_INFO_URL = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/info"

LOCAL_ONLY = {
    "ALTCOIN": ("", "#2563eb"),
    "DEBITO": ("", "#ef4444"),
    "DEFAULT": ("?", "#64748b"),
    "EUR": ("EUR", "#2563eb"),
}


def _load_api_key() -> str:
    load_dotenv(PROJECT_ROOT / "API_KEYS.env")
    return os.getenv("COINMARKETCAP_API_KEY", "")


def _portfolio_symbols() -> list[str]:
    portfolio_file = get_data_file("portfolio")
    if not portfolio_file.exists():
        portfolio_file = get_data_file("wallet_portfolio")

    with portfolio_file.open("r") as f:
        data = json.load(f)

    symbols = set()
    for balances in data.get("Portfolio", {}).values():
        if isinstance(balances, dict):
            symbols.update(balances.keys())

    symbols.update(LOCAL_ONLY)
    return sorted(symbols)


def _save_badge(symbol: str, text: str, color: str) -> None:
    TOKEN_ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = TOKEN_ICON_DIR / f"{symbol}.png"

    fig, ax = plt.subplots(figsize=(1, 1), dpi=160)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Circle((0.5, 0.5), 0.44, facecolor=color, edgecolor="none"))

    if text:
        size = 27 if len(text) <= 3 else 20
        ax.text(0.5, 0.5, text, ha="center", va="center", color="white", weight="bold", fontsize=size)
    fig.savefig(path, transparent=True, bbox_inches=None, pad_inches=0)
    plt.close(fig)


def _download(url: str, path: Path) -> bool:
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        path.write_bytes(response.content)
        return True
    except Exception:
        return False


def _fetch_cmc_logos(symbols: list[str]) -> dict[str, str]:
    api_key = _load_api_key()
    if not api_key:
        return {}

    query_symbols = [s for s in symbols if s not in LOCAL_ONLY and s != "EUR"]
    if not query_symbols:
        return {}

    response = requests.get(
        CMC_INFO_URL,
        headers={"X-CMC_PRO_API_KEY": api_key},
        params={"symbol": ",".join(query_symbols)},
        timeout=20,
    )
    response.raise_for_status()

    logos = {}
    for symbol, entries in (response.json().get("data") or {}).items():
        if isinstance(entries, list) and entries:
            logo = entries[0].get("logo")
            if logo:
                logos[symbol.upper()] = logo

    return logos


def update_token_icons(symbols: list[str] | None = None) -> dict[str, str]:
    TOKEN_ICON_DIR.mkdir(parents=True, exist_ok=True)
    symbols = symbols or _portfolio_symbols()

    result = {}
    cmc_logos = _fetch_cmc_logos(symbols)

    for symbol in symbols:
        symbol = symbol.upper()
        path = TOKEN_ICON_DIR / f"{symbol}.png"

        if symbol in cmc_logos and _download(cmc_logos[symbol], path):
            result[symbol] = "downloaded"
            continue

        text, color = LOCAL_ONLY.get(symbol, (symbol[:4], "#64748b"))
        _save_badge(symbol, text, color)
        result[symbol] = "badge"

    return result


def main() -> None:
    result = update_token_icons()
    for symbol, status in sorted(result.items()):
        print(f"{symbol}: {status}")


if __name__ == "__main__":
    main()
