import json
import time
import random
import requests
import httpx
import sys
from collections import defaultdict
from pathlib import Path
from pprint import pprint
from typing import Dict, Tuple, Optional

from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_wallet_address
from funzioniUtili import normalizza_tickername_solana

# === CONFIG ===
# Se hai un RPC con API key (consigliato):
# DEFAULT_SOLANA_RPC = "https://rpc.helius.xyz/?api-key=LA_TUA_API_KEY"
DEFAULT_SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SAVE_FINANCE_USER_OVERVIEW_URL = "https://api.save.finance/v1/user-overview"

LEDGER_SOL_ADDRESS = get_wallet_address("solana", "ledger")
PHANTOM_ADDRESS = get_wallet_address("solana", "phantom")

# Program IDs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"          # SPL classico
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"     # Token-2022

# Alcuni mint noti (fallback in assenza di token list)
KNOWN = {
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": ("WETH", "Ether (Portal)"),
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT", "Tether USD"),
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": ("cbBTC", "Coinbase Wrapped BTC"),
    "C7heQqfNzdMbUFQwcHkL9FvdwsFsDRBnfwZDDyWYCLTZ": ("COLLAT", "Collaterize"),
}

# Cache in-mem della token list di Jupiter
_TOKEN_MAP_CACHE: Optional[Dict[str, Tuple[Optional[str], Optional[str]]]] = None


# ---------- Retry helpers ----------
def _iter_causes(e: BaseException):
    """Itera lungo la catena delle cause/context dell'eccezione."""
    seen = set()
    cur = e
    while cur and id(cur) not in seen:
        yield cur
        seen.add(id(cur))
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)


def _is_rate_limited(e: BaseException) -> Tuple[bool, int]:
    """
    Rileva un 429 anche se incapsulato in altre eccezioni.
    Ritorna (is_429, retry_after_seconds).
    """
    for ex in _iter_causes(e):
        # Caso esplicito: 429 da httpx
        if isinstance(ex, httpx.HTTPStatusError):
            resp = getattr(ex, "response", None)
            if resp is not None and getattr(resp, "status_code", None) == 429:
                try:
                    ra = int(resp.headers.get("Retry-After", "0"))
                except Exception:
                    ra = 0
                return True, ra

        # Caso requests.HTTPError
        if isinstance(ex, requests.exceptions.HTTPError):
            resp = getattr(ex, "response", None)
            if resp is not None and getattr(resp, "status_code", None) == 429:
                try:
                    ra = int(resp.headers.get("Retry-After", "0"))
                except Exception:
                    ra = 0
                return True, ra

        # Fallback substring
        msg = str(ex).lower()
        if "429" in msg or "too many requests" in msg or "rate limit" in msg:
            return True, 0
    return False, 0


def _with_retries(fn, *args, max_retries=8, base_delay=1.0, max_delay=10.0, **kwargs):
    """
    Retry esponenziale + jitter.
    Riconosce 429 (anche incapsulato) e rispetta l'header Retry-After quando presente.
    """
    delay = base_delay
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            is429, retry_after = _is_rate_limited(e)
            msg = str(e).lower()
            transient = (
                is429
                or "timeout" in msg
                or "timed out" in msg
                or "connection aborted" in msg
                or "server disconnected" in msg
                or "temporary" in msg
            )
            if not transient or attempt == max_retries - 1:
                raise
            sleep_for = max(delay, retry_after or 0) + random.uniform(0, delay * 0.5)
            time.sleep(sleep_for)
            delay = min(max_delay, delay * 2)


def _get_with_retries(url: str, timeout: float = 10.0, max_retries: int = 4):
    def _do_get():
        r = requests.get(url, timeout=timeout)
        if r.status_code >= 400:
            r.raise_for_status()
        return r
    return _with_retries(_do_get, max_retries=max_retries)


# ---------- Token list ----------
def _load_token_map() -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    global _TOKEN_MAP_CACHE
    if _TOKEN_MAP_CACHE is not None:
        return _TOKEN_MAP_CACHE
    try:
        r = _get_with_retries("https://token.jup.ag/all", timeout=10, max_retries=4)
        data = r.json()
        _TOKEN_MAP_CACHE = {t["address"]: (t.get("symbol"), t.get("name")) for t in data}
    except Exception:
        _TOKEN_MAP_CACHE = {}
    return _TOKEN_MAP_CACHE


def _label_for_mint(mint: str, token_map: Dict[str, Tuple[Optional[str], Optional[str]]]):
    return token_map.get(mint) or KNOWN.get(mint) or (None, None)


# ---------- RPC helpers ----------
def _fetch_accounts_retry(client: Client, owner: Pubkey, program_id_str: str):
    """
    getTokenAccountsByOwner (jsonParsed) per uno specifico programma SPL,
    con retry + pre-jitter per evitare burst.
    """
    def _call():
        # anti-burst: piccolo jitter per non colpire sempre gli stessi slot
        time.sleep(random.uniform(0.3, 0.9))
        return client.get_token_accounts_by_owner_json_parsed(
            owner, TokenAccountOpts(program_id=Pubkey.from_string(program_id_str))
        )
    resp = _with_retries(_call, max_retries=8, base_delay=1.0, max_delay=10.0)
    return json.loads(resp.to_json())["result"]["value"]


def _get_balance_retry(client: Client, owner: Pubkey) -> int:
    def _call():
        return client.get_balance(owner)
    resp = _with_retries(_call, max_retries=6, base_delay=0.7, max_delay=6.0)
    return resp.value


# ---------- PUBBLICA: UN SOLO WALLET ----------
def get_wallet_holdings(
    address: str,
    *,
    show_zero: bool = False,
    rpc_endpoint: str = DEFAULT_SOLANA_RPC,
    include_token2022: bool = False
) -> Dict[str, float]:
    """
    Restituisce il DIZIONARIO FINALE per UN wallet:
        { token_symbol|name|mint : quantità }

    - Include 'SOL'
    - Aggrega più account dello stesso mint
    - Le chiavi privilegiano symbol, poi name, altrimenti il mint
    """
    client = Client(rpc_endpoint)
    owner = Pubkey.from_string(address)

    # === SOL ===
    lamports = _get_balance_retry(client, owner)
    sol_ui = lamports / 1_000_000_000

    holdings = defaultdict(float)
    if show_zero or sol_ui > 0:
        holdings["SOL"] += float(sol_ui)

    # === Token accounts ===
    token_map = _load_token_map()

    accounts = _fetch_accounts_retry(client, owner, TOKEN_PROGRAM_ID)

    if include_token2022:
        try:
            accounts += _fetch_accounts_retry(client, owner, TOKEN_2022_PROGRAM_ID)
        except Exception as e:
            # Se è 429 incapsulato, _with_retries avrà già backoffato il call;
            # qui ignoriamo solo eventuali hard-fail successivi legati al secondo programma.
            if "429" not in str(e):
                raise

    for item in accounts:
        info = item["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        amt_info = info["tokenAmount"]

        # uiAmount può essere None -> fallback calcolando da amount/decimals
        ui_amt = amt_info.get("uiAmount")
        if ui_amt is None:
            raw = amt_info.get("amount")
            decimals = int(amt_info.get("decimals") or 0)
            try:
                ui_amt = (int(raw) / (10 ** decimals)) if raw is not None else 0.0
            except Exception:
                ui_amt = 0.0

        if not show_zero and float(ui_amt) == 0.0:
            continue

        symbol, name = _label_for_mint(mint, token_map)
        key = normalizza_tickername_solana(symbol or name or mint, mint)
        holdings[key] += float(ui_amt)

    return dict(sorted(holdings.items()))


def get_save_finance_balances(address: str, verbose: bool = False) -> Dict[str, float]:
    """
    Legge le posizioni Save Finance/Solend del wallet.
    Depositi positivi, borrow negativi.
    """
    try:
        response = requests.get(
            SAVE_FINANCE_USER_OVERVIEW_URL,
            params={"wallet": address},
            timeout=20,
        )
        if response.status_code != 200:
            if verbose:
                print(f"Save Finance: HTTP {response.status_code} - {response.text[:250]}")
            return {}
        data = response.json()
    except Exception as exc:
        if verbose:
            print(f"Save Finance: errore richiesta - {exc}")
        return {}

    balances = defaultdict(float)
    active_markets = [market for market in data.values() if market]

    for market in active_markets:
        for deposit in market.get("deposits", []):
            symbol = deposit.get("symbol") or deposit.get("mint") or ""
            mint = deposit.get("mint") or ""
            try:
                amount = float(deposit.get("depositedAmount") or 0)
            except (TypeError, ValueError):
                continue
            if amount:
                balances[normalizza_tickername_solana(symbol, mint)] += amount

        for borrow in market.get("borrows", []):
            symbol = borrow.get("symbol") or borrow.get("mint") or ""
            mint = borrow.get("mint") or ""
            try:
                amount = float(borrow.get("borrowedAmount") or 0)
            except (TypeError, ValueError):
                continue
            if amount:
                balances[normalizza_tickername_solana(symbol, mint)] -= amount

    result = {k: v for k, v in sorted(balances.items()) if v != 0.0}
    if verbose:
        print(f"Save Finance: {len(active_markets)} market attivi, {len(result)} token netti")
    return result


def main() -> None:
    print("=== Test get_wallet_holdings() PHANTOM ===")

    phantom = get_wallet_holdings(
        PHANTOM_ADDRESS,
        show_zero=False,
        include_token2022=False,
    )

    if not phantom:
        print("Nessun saldo trovato.")
    else:
        pprint(phantom, sort_dicts=False)

    print("\n=== Test Save Finance PHANTOM ===")
    save_phantom = get_save_finance_balances(PHANTOM_ADDRESS, verbose=True)
    pprint(save_phantom, sort_dicts=False)


if __name__ == "__main__":
    main()
