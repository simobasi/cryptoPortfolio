import argparse
import csv
import json

from currency_converter import CurrencyConverter

from config import get_data_file
from funzioniUtili import get_crypto_price
from updatePORTFOLIO import updateData


def cmd_update(_args) -> None:
    data = updateData()
    print(f"Portfolio salvato: {', '.join(sorted(data['Portfolio'].keys()))}")


def cmd_view(_args) -> None:
    from viewPORTAFOGLIO import main as view_main

    view_main()


def cmd_test(args) -> None:
    target = args.target

    if target in ("eth", "all"):
        from Wallets.ethW import main as eth_main

        eth_main()

    if target in ("solana", "all"):
        from Wallets.solanaW import main as solana_main

        solana_main()

    if target in ("kraken", "all"):
        from Wallets.kraken import main as kraken_main

        kraken_main()

    if target in ("cdc", "all"):
        from Wallets.cdc import get_balances_cdc

        print("\n=== Test CDC ===")
        print(get_balances_cdc())


def cmd_export(_args) -> None:
    portfolio_file = get_data_file("portfolio")
    export_file = get_data_file("portfolio_export")

    if not portfolio_file.exists():
        updateData()

    with portfolio_file.open("r") as f:
        portfolio = json.load(f).get("Portfolio", {})

    usd_to_eur = CurrencyConverter().convert(1.0, "USD", "EUR")

    rows = []
    for wallet, balances in portfolio.items():
        if not isinstance(balances, dict):
            continue
        for token, quantity in balances.items():
            price_usd = float(get_crypto_price(token) or 0.0)
            value_eur = float(quantity) * price_usd * usd_to_eur
            rows.append(
                {
                    "wallet": wallet,
                    "token": token,
                    "quantity": quantity,
                    "value_eur": round(value_eur, 2),
                }
            )

    export_file.parent.mkdir(parents=True, exist_ok=True)
    with export_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["wallet", "token", "quantity", "value_eur"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Export salvato: {export_file}")


def cmd_icons(_args) -> None:
    from token_icons import update_token_icons

    result = update_token_icons()
    for symbol, status in sorted(result.items()):
        print(f"{symbol}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestione portfolio crypto")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser("update", help="Aggiorna e salva i dati portfolio")
    update_parser.set_defaults(func=cmd_update)

    view_parser = subparsers.add_parser("view", help="Apre il grafico portfolio")
    view_parser.set_defaults(func=cmd_view)

    test_parser = subparsers.add_parser("test", help="Testa una sorgente dati")
    test_parser.add_argument("target", choices=["eth", "solana", "kraken", "cdc", "all"])
    test_parser.set_defaults(func=cmd_test)

    export_parser = subparsers.add_parser("export", help="Esporta il portfolio in CSV")
    export_parser.set_defaults(func=cmd_export)

    icons_parser = subparsers.add_parser("icons", help="Scarica o rigenera le icone token locali")
    icons_parser.set_defaults(func=cmd_icons)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
