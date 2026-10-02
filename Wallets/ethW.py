from pprint import pprint
import os
import sys
from pathlib import Path
from web3 import Web3
import requests
from collections import defaultdict
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_wallet_address
from funzioniUtili import normalizza_tickername_eth

load_dotenv(PROJECT_ROOT / "API_KEYS.env")

# === CONFIG ===
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
WALLET_ADDRESS = get_wallet_address("ethereum", "ledger")

# === CHAIN INFO ===
chains = {
    'eth': "",  # Ethereum Mainnet
    'arbitrum': "arbitrum-"  # Arbitrum Mainnet
}
urls = {k: f"https://{p}mainnet.infura.io/v3/{INFURA_PROJECT_ID}" for k, p in chains.items()}

AAVE_ARBITRUM_DATA_PROVIDER = "0x243Aa95cAC2a25651eda86e80bEe66114413c43b"

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

AAVE_DATA_PROVIDER_ABI = [
    {
        "inputs": [],
        "name": "getAllReservesTokens",
        "outputs": [
            {
                "components": [
                    {"internalType": "string", "name": "symbol", "type": "string"},
                    {"internalType": "address", "name": "tokenAddress", "type": "address"},
                ],
                "internalType": "struct IPoolDataProvider.TokenData[]",
                "name": "",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "address", "name": "user", "type": "address"},
        ],
        "name": "getUserReserveData",
        "outputs": [
            {"internalType": "uint256", "name": "currentATokenBalance", "type": "uint256"},
            {"internalType": "uint256", "name": "currentStableDebt", "type": "uint256"},
            {"internalType": "uint256", "name": "currentVariableDebt", "type": "uint256"},
            {"internalType": "uint256", "name": "principalStableDebt", "type": "uint256"},
            {"internalType": "uint256", "name": "scaledVariableDebt", "type": "uint256"},
            {"internalType": "uint256", "name": "stableBorrowRate", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidityRate", "type": "uint256"},
            {"internalType": "uint40", "name": "stableRateLastUpdated", "type": "uint40"},
            {"internalType": "bool", "name": "usageAsCollateralEnabled", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


# === HELPERS ===
def get_native_balance(w3: Web3):
    if not w3.is_connected():
        return 0.0
    bal_wei = w3.eth.get_balance(WALLET_ADDRESS)
    return float(w3.from_wei(bal_wei, 'ether'))


def get_erc20_tokens(chain_key: str, verbose: bool = False) -> list:
    url = f"https://deep-index.moralis.io/api/v2.2/{WALLET_ADDRESS}/erc20?chain={chain_key}"
    headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            if verbose:
                print(f"Moralis {chain_key}: HTTP {r.status_code} - {r.text[:250]}")
            return []
        tokens = r.json()
        if verbose:
            print(f"Moralis {chain_key}: {len(tokens)} token ERC-20 trovati")
        return tokens
    except requests.RequestException as exc:
        if verbose:
            print(f"Moralis {chain_key}: errore richiesta - {exc}")
        return []


def get_aave_balances_arbitrum(verbose: bool = False) -> dict | None:
    w3 = Web3(Web3.HTTPProvider(urls["arbitrum"]))
    if not w3.is_connected():
        if verbose:
            print("Aave Arbitrum: RPC non connesso")
        return None

    wallet = Web3.to_checksum_address(WALLET_ADDRESS)
    data_provider = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_ARBITRUM_DATA_PROVIDER),
        abi=AAVE_DATA_PROVIDER_ABI,
    )

    try:
        reserves = data_provider.functions.getAllReservesTokens().call()
    except Exception as exc:
        if verbose:
            print(f"Aave Arbitrum: errore getAllReservesTokens - {exc}")
        return None

    balances = defaultdict(float)

    for symbol, token_address in reserves:
        try:
            token = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            decimals = int(token.functions.decimals().call())
            user_data = data_provider.functions.getUserReserveData(token_address, wallet).call()

            supply_raw = int(user_data[0])
            stable_debt_raw = int(user_data[1])
            variable_debt_raw = int(user_data[2])
            net_raw = supply_raw - stable_debt_raw - variable_debt_raw

            if net_raw:
                balances[normalizza_tickername_eth(symbol)] += net_raw / (10 ** decimals)
        except Exception as exc:
            if verbose:
                print(f"Aave Arbitrum: salto {symbol} ({token_address}) - {exc}")

    result = {k: v for k, v in balances.items() if v != 0.0}
    if verbose:
        print(f"Aave Arbitrum: {len(result)} token/debiti trovati")
    return result


def get_balances_eth(verbose: bool = False) -> tuple[dict, dict]:
    """
    Restituisce i saldi ETH già separati:
        AAVE, LEDGER_ETH

    La separazione resta qui perché dipende da come Moralis espone i token
    Aave/Arbitrum nel wallet Ethereum.
    """
    ledger_totals = defaultdict(float)
    moralis_aave_totals = defaultdict(float)

    # filtri basilari per spam
    bad_keywords = ["airdrop", "claim", "reward", "ticket", "fake"]
    manual_blacklist = {"ETHG", "ETHGAMES", "FAKECOIN", "SCAMDROP", "BOTS", "ARB-AIRDROP"}

    for chain_key, rpc_url in urls.items():
        # 1) ETH nativo → conta come ETH (somma su tutte le reti)
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        eth_native = get_native_balance(w3)
        if eth_native:
            ledger_totals["ETH"] += eth_native

        # 2) ERC-20
        tokens = get_erc20_tokens(chain_key, verbose=verbose)
        for t in tokens:
            name = (t.get("name") or "").strip()
            symbol = (t.get("symbol") or "").strip()
            if not name or not symbol:
                continue

            su = symbol.upper()
            if su in manual_blacklist:
                continue
            if any(bad in su.lower() for bad in bad_keywords) and "variabledebt" not in su.lower():
                continue

            decimals = int(t.get("decimals", 18) or 18)
            try:
                raw = int(t.get("balance", "0"))
            except (TypeError, ValueError):
                continue
            amount = raw / (10 ** decimals)
            if amount == 0:
                continue

            # Debito Aave → negativo
            if "variabledebt" in su.lower():
                amount = -abs(amount)

            if "arb" in symbol.casefold():
                moralis_aave_totals[normalizza_tickername_eth(symbol)] += float(amount)
            else:
                ledger_totals[normalizza_tickername_eth(symbol)] += float(amount)

    aave_direct = get_aave_balances_arbitrum(verbose=verbose)
    aave_totals = aave_direct if aave_direct is not None else moralis_aave_totals

    return (
        {k: v for k, v in aave_totals.items() if v != 0.0},
        {k: v for k, v in ledger_totals.items() if v != 0.0},
    )

def main() -> None:
    print("=== Test get_balances_eth() ===")
    print(f"Wallet: {WALLET_ADDRESS}")
    print(f"Chains: {list(urls.keys())}\n")

    try:
        aave, ledger_eth = get_balances_eth(verbose=True)
        balances = {
            "AAVE": aave,
            "LEDGER_ETH": ledger_eth,
        }
        if not aave and not ledger_eth:
            print("Nessun saldo trovato (o errore API/RPC).")
        else:
            pprint(balances, sort_dicts=False)

            print("\n=== Riepilogo ===")
            print(f"Token AAVE: {len(aave)}")
            print(f"Token LEDGER_ETH: {len(ledger_eth)}")
            if "ETH" in ledger_eth:
                print(f"ETH totale (somma reti): {ledger_eth['ETH']}")
    except Exception as e:
        print("Errore durante il test:", repr(e))


if __name__ == "__main__":
    main()
