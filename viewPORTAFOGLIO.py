import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from currency_converter import CurrencyConverter
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.widgets import CheckButtons

from config import PROJECT_ROOT, get_data_file
from funzioniUtili import get_crypto_price
from updatePORTFOLIO import updateData


DATA_FILE = get_data_file("portfolio")
WALLET_DATA_FILE = get_data_file("wallet_portfolio")
TOKEN_ICON_DIR = PROJECT_ROOT / "assets" / "tokens"

AGGIORNA_DATI = False
AGGREGA_ALTCOIN = True
SOGLIA_ALTCOIN = 4.0
SOGLIA_MIN_USD = 0.0


def getData(update: bool = True) -> dict:
    if update:
        return updateData()

    data_file = DATA_FILE if DATA_FILE.exists() else WALLET_DATA_FILE
    with data_file.open("r") as f:
        return json.load(f)


def fmt_eur(x: float, decimals: int = 0) -> str:
    segno = "-" if x < 0 else ""
    value = f"{abs(x):,.{decimals}f}"
    value = value.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{segno}{value} €"


def build_portfolio_frame(data: dict) -> pd.DataFrame:
    portfolio = data.get("Portfolio", {})
    if not portfolio:
        return pd.DataFrame()

    qraw = pd.DataFrame.from_dict(portfolio, orient="index").fillna(0.0)
    col_sums = qraw.sum(axis=0)
    return qraw.loc[:, col_sums.ne(0.0)]


def build_token_slices(
    valori_usd_token: pd.Series,
    quantita: pd.Series,
    usd_to_eur: float,
    aggrega_altcoin: bool,
):
    eur_usd = float(valori_usd_token.get("EUR", 0.0))
    valori_crypto = valori_usd_token.drop(labels=["EUR"], errors="ignore")

    filtrati = valori_crypto[valori_crypto > SOGLIA_MIN_USD].sort_values(ascending=False)
    neg = valori_crypto[valori_crypto < 0]
    debito_tot = float(neg.sum() + eur_usd)
    debito_abs = abs(debito_tot) if debito_tot < 0 else 0.0

    fette_token = filtrati.copy()
    if debito_abs > 0:
        fette_token.loc["DEBITO"] = debito_abs

    if fette_token.sum() <= 0:
        return None, None

    piccoli_idx = pd.Index([])
    fette_token_finali = fette_token.copy()

    if aggrega_altcoin:
        totale_torta = float(fette_token.sum())
        token_solo = fette_token.drop(labels=["DEBITO"], errors="ignore")
        percentuali = (token_solo / totale_torta) * 100.0
        piccoli_idx = percentuali.index[percentuali < SOGLIA_ALTCOIN]

        altcoin_sum = float(token_solo.loc[piccoli_idx].sum()) if len(piccoli_idx) else 0.0
        fette_token_finali = fette_token.drop(index=piccoli_idx, errors="ignore")
        if altcoin_sum > 0:
            fette_token_finali.loc["ALTCOIN"] = altcoin_sum

    fette_token_finali = fette_token_finali.sort_values(ascending=False)
    labels_token = [
        (
            f"DEBITO ({fmt_eur(debito_tot * usd_to_eur)})"
            if n == "DEBITO"
            else f"ALTCOIN ({len(piccoli_idx)} token, {fmt_eur(fette_token_finali.get(n, 0.0) * usd_to_eur)})"
            if n == "ALTCOIN"
            else f"{n} {quantita.get(n, 0.0):g} ({fmt_eur(fette_token_finali.get(n, 0.0) * usd_to_eur)})"
        )
        for n in fette_token_finali.index
    ]
    return fette_token_finali, labels_token


def get_token_icon_path(symbol: str) -> Path:
    path = TOKEN_ICON_DIR / f"{symbol}.png"
    if path.exists():
        return path
    return TOKEN_ICON_DIR / "DEFAULT.png"


def draw_token_legend(ax, token_symbols, labels_token) -> None:
    ax.clear()
    ax.axis("off")
    ax.set_title("Token", loc="left", fontsize=11)

    if not labels_token:
        return

    row_height = min(0.072, 0.78 / max(len(labels_token), 1))
    y = 0.84

    for symbol, label in zip(token_symbols, labels_token):
        icon_path = get_token_icon_path(symbol)
        try:
            image = plt.imread(icon_path)
            zoom = 0.095 if symbol in {"DEBITO", "ALTCOIN"} else 0.13
            imagebox = OffsetImage(image, zoom=zoom)
            ab = AnnotationBbox(
                imagebox,
                (0.06, y),
                xycoords=ax.transAxes,
                frameon=False,
                box_alignment=(0.5, 0.5),
            )
            ax.add_artist(ab)
        except Exception:
            pass

        ax.text(
            0.13,
            y,
            label,
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=8,
        )
        y -= row_height


def draw_token_pie(
    ax,
    legend_ax,
    valori_usd_token: pd.Series,
    quantita: pd.Series,
    usd_to_eur: float,
    aggrega_altcoin: bool,
) -> None:
    ax.clear()
    legend_ax.clear()
    fette_token_finali, labels_token = build_token_slices(
        valori_usd_token,
        quantita,
        usd_to_eur,
        aggrega_altcoin,
    )

    if fette_token_finali is None or fette_token_finali.sum() <= 0:
        ax.text(0.5, 0.5, "Nessun dato disponibile", ha="center", va="center")
        ax.axis("off")
        legend_ax.axis("off")
        return

    ax.pie(
        fette_token_finali.values,
        labels=None,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.75,
    )
    ax.axis("equal")
    ax.set_title("Ripartizione per Token")
    draw_token_legend(legend_ax, fette_token_finali.index.tolist(), labels_token)


def main() -> None:
    data = getData(update=AGGIORNA_DATI)
    qraw = build_portfolio_frame(data)

    if qraw.empty:
        print("Nessun dato portfolio disponibile.")
        return

    quantita = qraw.sum(axis=0).astype(float)

    simboli_utili = quantita.index.tolist()
    prezzi = pd.Series({s: float(get_crypto_price(s) or 0.0) for s in simboli_utili})

    qval = qraw.mul(prezzi, axis=1)
    valori_usd_token = qval.sum(axis=0)
    valori_usd_wallet = qval.sum(axis=1)

    usd_to_eur = CurrencyConverter().convert(1.0, "USD", "EUR")
    totale_usd_netto = float(valori_usd_token.sum())
    totale_eur_netto = totale_usd_netto * usd_to_eur

    prezzo_btc_usd = float(prezzi.get("BTC", 0.0)) or float(get_crypto_price("BTC") or 0.0)
    btc_equiv = (totale_usd_netto / prezzo_btc_usd) if prezzo_btc_usd else 0.0
    titolo = f"Valore Portfolio: {fmt_eur(totale_eur_netto, decimals=2)} / {btc_equiv:.4f} BTC"

    wallet_pie = valori_usd_wallet[valori_usd_wallet > 0].sort_values(ascending=False)

    fig = plt.figure(figsize=(16, 7))
    grid = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.05, 0.9])
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    legend_ax = fig.add_subplot(grid[0, 2])

    if wallet_pie.sum() > 0:
        axes[0].pie(
            wallet_pie.values,
            labels=wallet_pie.index,
            autopct="%1.1f%%",
            startangle=90,
            labeldistance=1.05,
            pctdistance=0.8,
        )
        axes[0].axis("equal")
        axes[0].set_title("Ripartizione per Wallet")
    else:
        axes[0].text(0.5, 0.5, "Nessun valore positivo", ha="center", va="center")
        axes[0].axis("off")

    stato = {"aggrega_altcoin": AGGREGA_ALTCOIN}
    draw_token_pie(axes[1], legend_ax, valori_usd_token, quantita, usd_to_eur, stato["aggrega_altcoin"])

    check_ax = fig.add_axes([0.78, 0.03, 0.18, 0.08])
    check = CheckButtons(check_ax, ["Aggrega altcoin"], [stato["aggrega_altcoin"]])

    def on_toggle(_label):
        stato["aggrega_altcoin"] = not stato["aggrega_altcoin"]
        draw_token_pie(axes[1], legend_ax, valori_usd_token, quantita, usd_to_eur, stato["aggrega_altcoin"])
        fig.canvas.draw_idle()

    check.on_clicked(on_toggle)

    fig.suptitle(titolo, fontsize=14)
    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.88, wspace=0.22)
    plt.show()


if __name__ == "__main__":
    main()
