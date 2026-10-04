import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from currency_converter import CurrencyConverter
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Polygon, Rectangle
from matplotlib.widgets import CheckButtons

from config import PROJECT_ROOT, get_data_file
from funzioniUtili import get_crypto_price
from updatePORTFOLIO import updateData


DATA_FILE = get_data_file("portfolio")
WALLET_DATA_FILE = get_data_file("wallet_portfolio")
TOKEN_ICON_DIR = PROJECT_ROOT / "assets" / "tokens"

AGGIORNA_DATI = False
AGGREGA_ALTCOIN = True
INCLUDI_IMMOBILI = False
SOGLIA_ALTCOIN = 4.0
SOGLIA_MIN_USD = 0.0
WALLET_IMMOBILI = "PRIMA CASA"
TOKEN_IMMOBILI = "IMMOBILI"


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
        token_solo = fette_token.drop(labels=["DEBITO", TOKEN_IMMOBILI], errors="ignore")
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
            else f"IMMOBILI ({fmt_eur(fette_token_finali.get(n, 0.0) * usd_to_eur)})"
            if n == TOKEN_IMMOBILI
            else f"{n} {quantita.get(n, 0.0):g} ({fmt_eur(fette_token_finali.get(n, 0.0) * usd_to_eur)})"
        )
        for n in fette_token_finali.index
    ]
    return fette_token_finali, labels_token


def get_token_icon_path(symbol: str) -> Path:
    if symbol == TOKEN_IMMOBILI:
        path = TOKEN_ICON_DIR / "IMMOBILI.png"
        if not path.exists():
            create_house_icon(path)
        return path

    path = TOKEN_ICON_DIR / f"{symbol}.png"
    if path.exists():
        return path
    return TOKEN_ICON_DIR / "DEFAULT.png"


def create_house_icon(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(1, 1), dpi=96)
    fig.patch.set_alpha(0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    circle = plt.Circle((0.5, 0.5), 0.48, color="#2563eb")
    ax.add_patch(circle)
    roof = Polygon(
        [(0.22, 0.50), (0.50, 0.76), (0.78, 0.50)],
        closed=True,
        facecolor="white",
        edgecolor="white",
        linewidth=2,
    )
    body = Rectangle(
        (0.30, 0.28),
        0.40,
        0.28,
        facecolor="white",
        edgecolor="white",
        linewidth=2,
    )
    door = Rectangle((0.46, 0.28), 0.10, 0.18, facecolor="#2563eb", edgecolor="#2563eb")
    ax.add_patch(roof)
    ax.add_patch(body)
    ax.add_patch(door)

    fig.savefig(path, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


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


def draw_wallet_pie(ax, valori_usd_wallet: pd.Series) -> None:
    ax.clear()
    wallet_pie = valori_usd_wallet[valori_usd_wallet > 0].sort_values(ascending=False)

    if wallet_pie.sum() > 0:
        ax.pie(
            wallet_pie.values,
            labels=wallet_pie.index,
            autopct="%1.1f%%",
            startangle=90,
            labeldistance=1.05,
            pctdistance=0.8,
        )
        ax.axis("equal")
        ax.set_title("Ripartizione per Wallet")
    else:
        ax.text(0.5, 0.5, "Nessun valore positivo", ha="center", va="center")
        ax.axis("off")


def get_patrimonio_immobiliare_eur() -> float:
    try:
        from patrimonio_casa import (
            QUOTA_COSTI_DEFAULT,
            QUOTA_DEBITO_DEFAULT,
            QUOTA_PROPRIETA_DEFAULT,
            VALORE_CASA_DEFAULT,
            patrimonio,
        )

        result = patrimonio(
            date.today(),
            VALORE_CASA_DEFAULT,
            QUOTA_PROPRIETA_DEFAULT,
            QUOTA_DEBITO_DEFAULT,
            QUOTA_COSTI_DEFAULT,
            parte_finale_override=None,
            notaio_override=None,
            debito_zero_prima_stipula=False,
        )
        return float(result["netto_tua_quota"])
    except Exception as exc:
        print(f"Patrimonio immobiliare non disponibile: {exc}")
        return 0.0


def add_patrimonio_immobiliare(
    valori_usd_token: pd.Series,
    valori_usd_wallet: pd.Series,
    patrimonio_immobiliare_eur: float,
    usd_to_eur: float,
    includi_immobili: bool,
) -> tuple[pd.Series, pd.Series]:
    valori_token = valori_usd_token.copy()
    valori_wallet = valori_usd_wallet.copy()

    if includi_immobili and patrimonio_immobiliare_eur > 0 and usd_to_eur:
        patrimonio_usd = patrimonio_immobiliare_eur / usd_to_eur
        valori_token.loc[TOKEN_IMMOBILI] = valori_token.get(TOKEN_IMMOBILI, 0.0) + patrimonio_usd
        valori_wallet.loc[WALLET_IMMOBILI] = valori_wallet.get(WALLET_IMMOBILI, 0.0) + patrimonio_usd

    return valori_token, valori_wallet


def build_title(
    totale_usd_netto: float,
    usd_to_eur: float,
    prezzo_btc_usd: float,
    includi_immobili: bool,
) -> str:
    totale_eur_netto = totale_usd_netto * usd_to_eur
    btc_equiv = (totale_usd_netto / prezzo_btc_usd) if prezzo_btc_usd else 0.0
    label = "Valore Portfolio + Immobili" if includi_immobili else "Valore Portfolio"
    return f"{label}: {fmt_eur(totale_eur_netto, decimals=2)} / {btc_equiv:.4f} BTC"


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
    prezzo_btc_usd = float(prezzi.get("BTC", 0.0)) or float(get_crypto_price("BTC") or 0.0)
    patrimonio_immobiliare_eur = get_patrimonio_immobiliare_eur()

    fig = plt.figure(figsize=(16, 7))
    grid = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.05, 0.9])
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    legend_ax = fig.add_subplot(grid[0, 2])

    stato = {
        "aggrega_altcoin": AGGREGA_ALTCOIN,
        "includi_immobili": INCLUDI_IMMOBILI,
    }

    def redraw() -> None:
        valori_token_view, valori_wallet_view = add_patrimonio_immobiliare(
            valori_usd_token,
            valori_usd_wallet,
            patrimonio_immobiliare_eur,
            usd_to_eur,
            stato["includi_immobili"],
        )
        draw_wallet_pie(axes[0], valori_wallet_view)
        draw_token_pie(
            axes[1],
            legend_ax,
            valori_token_view,
            quantita,
            usd_to_eur,
            stato["aggrega_altcoin"],
        )
        fig.suptitle(
            build_title(
                float(valori_token_view.sum()),
                usd_to_eur,
                prezzo_btc_usd,
                stato["includi_immobili"],
            ),
            fontsize=14,
        )

    redraw()

    check_ax = fig.add_axes([0.74, 0.03, 0.23, 0.10])
    check = CheckButtons(
        check_ax,
        ["Aggrega altcoin", "Includi immobili"],
        [stato["aggrega_altcoin"], stato["includi_immobili"]],
    )

    def on_toggle(label):
        if label == "Aggrega altcoin":
            stato["aggrega_altcoin"] = not stato["aggrega_altcoin"]
        elif label == "Includi immobili":
            stato["includi_immobili"] = not stato["includi_immobili"]
        redraw()
        fig.canvas.draw_idle()

    check.on_clicked(on_toggle)

    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.88, wspace=0.22)
    plt.show()


if __name__ == "__main__":
    main()
