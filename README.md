# Crypto Portfolio

Dashboard locale per aggiornare e visualizzare un portfolio crypto da wallet/API diverse.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item API_KEYS.example.env API_KEYS.env
```

Poi compila `API_KEYS.env` con chiavi API e address wallet.

## Comandi

```powershell
.\.venv\Scripts\python.exe portfolio.py update
.\.venv\Scripts\python.exe portfolio.py view
.\.venv\Scripts\python.exe portfolio.py icons
.\.venv\Scripts\python.exe portfolio.py export
```

Test singole sorgenti:

```powershell
.\.venv\Scripts\python.exe portfolio.py test eth
.\.venv\Scripts\python.exe portfolio.py test solana
.\.venv\Scripts\python.exe portfolio.py test kraken
.\.venv\Scripts\python.exe portfolio.py test all
```

## File sensibili

`API_KEYS.env` contiene chiavi API e wallet/account. Non va caricato su GitHub.

Sono esclusi anche i dati generati in `data/`, `Wallets/portafoglio.json`, backup locali e cache Python.
