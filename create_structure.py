from pathlib import Path

# Główna ścieżka projektu
BASE_DIR = Path(r"C:\Users\sakla\OneDrive\Pulpit\PROJECTS\Internet_data_extraction")

# Foldery do utworzenia
folders = [
    "data/raw/esa",
    "data/raw/gios",
    "data/raw/weather",
    "data/processed",
    "data/database",
    "logs",
    "src",
    "notebooks"
]

# Pliki do utworzenia
files = [
    "main.py",
    "requirements.txt",
    "README.md",
    "src/__init__.py",
    "src/config.py",
    "src/extract_esa.py",
    "src/extract_gios.py",
    "src/extract_weather.py",
    "src/database.py",
    "src/transform.py",
    "src/utils.py"
]

# Tworzenie folderów
for folder in folders:
    path = BASE_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    print(f"Utworzono folder: {path}")

# Tworzenie plików
for file in files:
    path = BASE_DIR / file
    path.touch(exist_ok=True)
    print(f"Utworzono plik: {path}")

print("\nGotowe! Struktura projektu została utworzona.")