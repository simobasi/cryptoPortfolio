import shutil
from pathlib import Path
from datetime import date


PROJECT_ROOT = Path(__file__).resolve().parent
BACKUP_DIR = PROJECT_ROOT / f"crypto_backup_{date.today().isoformat()}"

FILES = [
    "portfolio.py",
    "config.py",
    "config.json",
    "updatePORTFOLIO.py",
    "viewPORTAFOGLIO.py",
    "wiewPORTAFOGLIO.py",
    "funzioniUtili.py",
    "token_icons.py",
    "requirements.txt",
    "API_KEYS.env",
    "chiavi(non cancellare).png",
]

DIRS = [
    "Wallets",
    "data",
    "assets",
]

EXCLUDED_DIRS = {
    "__pycache__",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
}


def _ignore(_dir, names):
    ignored = set()
    for name in names:
        path = Path(name)
        if name in EXCLUDED_DIRS or path.suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def build_backup() -> Path:
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    BACKUP_DIR.mkdir(parents=True)

    for file_name in FILES:
        source = PROJECT_ROOT / file_name
        if source.exists():
            target = BACKUP_DIR / file_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    for dir_name in DIRS:
        source = PROJECT_ROOT / dir_name
        if source.exists():
            shutil.copytree(source, BACKUP_DIR / dir_name, ignore=_ignore)

    return BACKUP_DIR


def main() -> None:
    backup_dir = build_backup()
    print(f"Backup creato: {backup_dir}")


if __name__ == "__main__":
    main()
