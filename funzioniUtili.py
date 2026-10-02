from collections import defaultdict
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / "API_KEYS.env")


def merge_and_sum(dict1, dict2):
    merged = {}
    for k in set(dict1) | set(dict2):
        merged[k] = dict1.get(k, 0) + dict2.get(k, 0)
    return merged


def normalizza_tickername_generico(ticker: str, name: str = "") -> str:
    """
    Normalizzazione comune per ticker equivalenti tra wallet diversi.
    I casi specifici dei singoli wallet possono fare preprocessing e poi
    passare da qui.
    """
    symbol = (ticker or "").strip()
    symbol_upper = symbol.upper().replace("₮", "T")
    name_upper = (name or "").upper()

    alias = {
        "XBT": "BTC",
        "XXBT": "BTC",
        "WBTC": "BTC",
        "AWBTC": "BTC",
        "ARBWBTC": "BTC",
        "TBTC": "BTC",
        "CBBTC": "BTC",
        "XETH": "ETH",
        "WETH": "ETH",
        "AETH": "ETH",
        "ARBWETH": "ETH",
        "STETH": "ETH",
        "ETH2": "ETH",
        "ETH2.S": "ETH",
        "USDT0": "USDT",
        "USDTE": "USDT",
        "USDT.E": "USDT",
        "USDC.E": "USDC",
        "USDCN": "USDC",
        "WSOL": "SOL",
        "W-SOL": "SOL",
    }

    if symbol_upper in alias:
        return alias[symbol_upper]

    if (
        any(x in symbol_upper for x in ["WBTC", "AWBTC", "ARBWBTC", "TBTC", "CBBTC"])
        or "WRAPPED BITCOIN" in name_upper
        or "COINBASE WRAPPED BTC" in name_upper
    ):
        return "BTC"

    if (
        any(x in symbol_upper for x in ["WETH", "AETH", "ARBWETH", "STETH", "ETH2"])
        or "WRAPPED ETHER" in name_upper
    ):
        return "ETH"

    return symbol_upper


def normalizza_tickername_kraken(ticker: str, name: str = "") -> str:
    """
    Kraken usa codici proprietari e suffissi:
    - XXBT/XBT -> BTC
    - XETH/ETH2.S -> ETH
    - ZEUR/ZUSD -> EUR/USD
    - HYPE.B, MON.B, BSPX.T -> HYPE, MON, BSPX
    """
    symbol = (ticker or "").strip().upper()
    base = symbol.split(".", 1)[0]

    alias = {
        "XBT": "BTC",
        "XXBT": "BTC",
        "XETH": "ETH",
        "ETH2": "ETH",
        "ZEUR": "EUR",
        "ZUSD": "USD",
        "ZGBP": "GBP",
        "ZAUD": "AUD",
        "ZCAD": "CAD",
        "ZJPY": "JPY",
        "XXDG": "DOGE",
        "XLTC": "LTC",
        "XXRP": "XRP",
    }

    return alias.get(base, normalizza_tickername_generico(base, name))


def normalizza_tickername_solana(ticker: str, name: str = "") -> str:
    mint_or_name = (name or "").strip()
    mint_alias = {
        "So11111111111111111111111111111111111111112": "SOL",
        "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": "BTC",
        "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ETH",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    }

    if mint_or_name in mint_alias:
        return mint_alias[mint_or_name]

    return normalizza_tickername_generico(ticker, name)


def normalizza_tickername_eth(ticker: str, name: str = "") -> str:
    return normalizza_tickername_generico(ticker, name)


def normalizza_portafoglio(data: dict, normalizza_tickername=normalizza_tickername_generico):
    grouped = defaultdict(float)

    for ticker, value in data.items():
        normalized = normalizza_tickername(ticker)
        if not normalized:
            continue

        try:
            amount = float(value)
        except (TypeError, ValueError):
            continue

        grouped[normalized] += amount

    return {k: v for k, v in grouped.items() if v != 0.0}


def map_and_sum_keys(data, mapping_keywords):
    """
    data: dict con chiavi e valori numerici
    mapping_keywords: lista di sottostringhe da raggruppare, es. ["BTC", "ETH", "USDT", "USDC"]
    """
    grouped = defaultdict(float)

    for key, value in data.items():
        normalized_key = normalizza_tickername_generico(key)
        key_upper = normalized_key.upper()
        matched = False

        for kw in mapping_keywords:
            if kw.upper() in key_upper:
                grouped[kw.upper()] += value
                matched = True
                break

        if not matched:
            grouped[normalized_key] += value

    return dict(grouped)


def get_crypto_price(crypto):
    crypto = normalizza_tickername_generico(crypto)

    if crypto == "USD":
        return 1.0

    if crypto == "EUR":
        try:
            from currency_converter import CurrencyConverter

            return float(CurrencyConverter().convert(1.0, "EUR", "USD"))
        except Exception:
            return 0.0

    api_key = os.getenv("COINMARKETCAP_API_KEY")
    if not api_key:
        return 0.0

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    parameters = {"symbol": crypto, "convert": "USD"}
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': api_key,
    }

    try:
        response = requests.get(url, headers=headers, params=parameters, timeout=10)
        data = response.json()
        if "data" not in data or crypto not in data["data"]:
            return 0.0
        return data["data"][crypto]["quote"]["USD"]["price"]
    except Exception:
        return 0.0


