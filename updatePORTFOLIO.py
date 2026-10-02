import json

from config import get_data_file
from Wallets.ethW import get_balances_eth
from Wallets.solanaW import (
    LEDGER_SOL_ADDRESS,
    PHANTOM_ADDRESS,
    get_save_finance_balances,
    get_wallet_holdings,
)
from Wallets.cdc import get_balances_cdc
from Wallets.kraken import get_balances_kraken

from funzioniUtili import (
    map_and_sum_keys,
    merge_and_sum,
    normalizza_portafoglio,
    normalizza_tickername_kraken,
)

PORTFOLIO_FILE = get_data_file("portfolio")
RAW_SOURCES_FILE = get_data_file("raw_sources")
WALLET_PORTFOLIO_FILE = get_data_file("wallet_portfolio")


def _safe_balances(label: str, fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        print(f"{label}: {exc}")
        return {}


def updateData():
    dati = {"Portfolio": {}}
    raw_sources = {}

    LEDGER_SOL = _safe_balances(
        "LEDGER_SOL",
        get_wallet_holdings,
        LEDGER_SOL_ADDRESS,
        show_zero=False,
        include_token2022=False,
    )
    raw_sources["LEDGER_SOL"] = LEDGER_SOL
    PHANTOM = _safe_balances(
        "PHANTOM",
        get_wallet_holdings,
        PHANTOM_ADDRESS,
        show_zero=False,
        include_token2022=False,
    )
    raw_sources["PHANTOM"] = PHANTOM
    dati["Portfolio"]["PHANTOM"] = map_and_sum_keys(PHANTOM, ["BTC", "ETH", "USDT", "USDC"])

    KRAKEN = _safe_balances("KRAKEN", get_balances_kraken, normalize=False)
    raw_sources["KRAKEN"] = KRAKEN
    dati["Portfolio"]["KRAKEN"] = normalizza_portafoglio(KRAKEN, normalizza_tickername_kraken)

    try:
        AAVE, LEDGER_ETH = get_balances_eth()
    except Exception as exc:
        print(f"ETH/AAVE: {exc}")
        AAVE, LEDGER_ETH = {}, {}
    raw_sources["AAVE"] = AAVE
    raw_sources["LEDGER_ETH"] = LEDGER_ETH
    LEDGER = merge_and_sum(LEDGER_ETH, LEDGER_SOL)
    dati["Portfolio"]["LEDGER"] = map_and_sum_keys(LEDGER, ["BTC", "ETH", "USDT", "USDC"])
    dati["Portfolio"]["AAVE"] = map_and_sum_keys(AAVE, ["BTC", "ETH", "USDT", "USDC"])

    SAVE_LEDGER = _safe_balances("SAVE_LEDGER", get_save_finance_balances, LEDGER_SOL_ADDRESS)
    SAVE_PHANTOM = _safe_balances("SAVE_PHANTOM", get_save_finance_balances, PHANTOM_ADDRESS)
    raw_sources["SAVE_LEDGER"] = SAVE_LEDGER
    raw_sources["SAVE_PHANTOM"] = SAVE_PHANTOM
    SAVE = merge_and_sum(SAVE_LEDGER, SAVE_PHANTOM)
    dati["Portfolio"]["SAVE"] = map_and_sum_keys(SAVE, ["BTC", "ETH", "USDT", "USDC"])

    CDC = _safe_balances("CDC", get_balances_cdc)
    raw_sources["CDC"] = CDC
    dati["Portfolio"]["CDC"] = map_and_sum_keys(CDC, ["BTC", "ETH", "USDT", "USDC"])

    dati["Portfolio"] = {
        wallet: balances
        for wallet, balances in dati["Portfolio"].items()
        if balances
    }

    PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    WALLET_PORTFOLIO_FILE.parent.mkdir(parents=True, exist_ok=True)

    raw_sources = {source: balances for source, balances in raw_sources.items() if balances}

    with PORTFOLIO_FILE.open("w") as f:
        json.dump(dati, f, indent=4)

    with RAW_SOURCES_FILE.open("w") as f:
        json.dump(raw_sources, f, indent=4)

    with WALLET_PORTFOLIO_FILE.open("w") as f:
        json.dump(dati, f, indent=4)

    return dati


def main() -> None:
    data = updateData()
    print(f"Portfolio salvato: {', '.join(sorted(data['Portfolio'].keys()))}")


if __name__ == "__main__":
    main()
