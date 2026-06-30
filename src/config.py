from pathlib import Path

# ============================================================
# GŁÓWNE ŚCIEŻKI PROJEKTU
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DATABASE_DIR = DATA_DIR / "database"
LOGS_DIR = BASE_DIR / "logs"

RAW_ESA_DIR = RAW_DIR / "esa"
RAW_GIOS_DIR = RAW_DIR / "gios"
RAW_WEATHER_DIR = RAW_DIR / "weather"

# ============================================================
# ENDPOINTY API
# ============================================================

ESA_API_URL = "https://public-esa.ose.gov.pl/api/v1/smog"

# ============================================================
# USTAWIENIA POBIERANIA
# ============================================================

REQUEST_TIMEOUT_SECONDS = 60
ESA_MAX_PAGES = 100
ESA_PAGE_DELAY_SECONDS = 0.2

# ============================================================
# ŚCIEŻKI DO PLIKÓW WYNIKOWYCH
# ============================================================

ESA_PROCESSED_CSV = PROCESSED_DIR / "esa_latest.csv"
ESA_STATIONS_CSV = PROCESSED_DIR / "esa_stations.csv"
ESA_MEASUREMENTS_CSV = PROCESSED_DIR / "esa_measurements.csv"

DATABASE_PATH = DATABASE_DIR / "environmental_data.duckdb"

# ============================================================
# TWORZENIE FOLDERÓW, JEŻELI NIE ISTNIEJĄ
# ============================================================

for directory in [
    DATA_DIR,
    RAW_DIR,
    PROCESSED_DIR,
    DATABASE_DIR,
    LOGS_DIR,
    RAW_ESA_DIR,
    RAW_GIOS_DIR,
    RAW_WEATHER_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# ENDPOINTY GIOŚ
# ============================================================

GIOS_API_BASE_URL = "https://api.gios.gov.pl/pjp-api/v1/rest"
GIOS_STATIONS_URL = f"{GIOS_API_BASE_URL}/station/findAll"

# ============================================================
# USTAWIENIA GIOŚ
# ============================================================

GIOS_PAGE_SIZE = 500
GIOS_MAX_PAGES = 20
GIOS_PAGE_DELAY_SECONDS = 0.5

# ============================================================
# ŚCIEŻKI DO PLIKÓW GIOŚ
# ============================================================

GIOS_STATIONS_CSV = PROCESSED_DIR / "gios_stations.csv"

# ============================================================
# ŚCIEŻKI DO PLIKÓW WYNIKOWYCH
# ============================================================

ESA_GIOS_NEAREST_CSV = PROCESSED_DIR / "esa_gios_nearest_stations.csv"

# ============================================================
# PRZYBLIŻONY ZAKRES WSPÓŁRZĘDNYCH POLSKI
# ============================================================

POLAND_MIN_LAT = 49.0
POLAND_MAX_LAT = 55.2
POLAND_MIN_LON = 14.0
POLAND_MAX_LON = 24.5

# ============================================================
# ENDPOINTY IMGW
# ============================================================

IMGW_SYNOP_URL = "https://danepubliczne.imgw.pl/api/data/synop"

# ============================================================
# ŚCIEŻKI DO PLIKÓW IMGW / WEATHER
# ============================================================

IMGW_WEATHER_CSV = PROCESSED_DIR / "imgw_weather_latest.csv"

# ============================================================
# GEOKODOWANIE STACJI IMGW
# ============================================================

IMGW_GEOCODING_CACHE_JSON = RAW_WEATHER_DIR / "imgw_geocoding_cache.json"

# ============================================================
# LOKALIZACJE STACJI IMGW
# ============================================================

IMGW_STATIONS_METADATA_CSV = PROCESSED_DIR / "imgw_weather_stations.csv"

# ============================================================
# INTEGRACJA ESA + IMGW
# ============================================================

ESA_IMGW_NEAREST_CSV = PROCESSED_DIR / "esa_imgw_nearest_weather.csv"

# ============================================================
# FINALNY ZBIÓR ANALITYCZNY
# ============================================================

ENVIRONMENTAL_SNAPSHOT_CSV = PROCESSED_DIR / "environmental_snapshot.csv"