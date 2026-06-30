import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from geopy.location import Location

from src.config import (
    IMGW_GEOCODING_CACHE_JSON,
    IMGW_STATIONS_METADATA_CSV,
    POLAND_MAX_LAT,
    POLAND_MAX_LON,
    POLAND_MIN_LAT,
    POLAND_MIN_LON,
)
from src.database import get_connection
from src.utils import setup_logger


logger = setup_logger(__name__)


def _safe_text(value: Any) -> str:
    """
    Zamienia wartość na bezpieczny tekst.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def _load_geocoding_cache() -> dict[str, Any]:
    """
    Wczytuje lokalny cache geokodowania.

    Dzięki temu przy kolejnym uruchomieniu nie pytamy ponownie
    o te same stacje.
    """

    if not IMGW_GEOCODING_CACHE_JSON.exists():
        return {}

    try:
        with open(IMGW_GEOCODING_CACHE_JSON, "r", encoding="utf-8") as file:
            cache = json.load(file)

    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Nie udało się odczytać cache geokodowania IMGW: %s", error)
        return {}

    if not isinstance(cache, dict):
        logger.warning("Cache geokodowania IMGW nie jest słownikiem. Tworzę pusty cache.")
        return {}

    return cache


def _save_geocoding_cache(cache: dict[str, Any]) -> None:
    """
    Zapisuje lokalny cache geokodowania.
    """

    try:
        with open(IMGW_GEOCODING_CACHE_JSON, "w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False, indent=2)

    except OSError as error:
        logger.warning("Nie udało się zapisać cache geokodowania IMGW: %s", error)


def _is_coordinate_in_poland(latitude: float, longitude: float) -> bool:
    """
    Sprawdza, czy współrzędne znajdują się w przybliżonym zakresie Polski.
    """

    return (
        POLAND_MIN_LAT <= latitude <= POLAND_MAX_LAT
        and POLAND_MIN_LON <= longitude <= POLAND_MAX_LON
    )


def _clean_station_name_for_query(station_name: str) -> str:
    """
    Czyści nazwę stacji przed geokodowaniem.
    """

    text = _safe_text(station_name)

    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return text


def _generate_geocoding_queries(station_name: str) -> list[str]:
    """
    Tworzy kilka wariantów zapytania geokodującego.

    Niektóre stacje IMGW mają nazwy z myślnikiem, np. KOŁOBRZEG-DŹWIRZYNO.
    Dlatego próbujemy kilku wersji.
    """

    cleaned_name = _clean_station_name_for_query(station_name)

    candidates = []

    if cleaned_name:
        candidates.append(f"{cleaned_name}, Polska")

    if "-" in cleaned_name:
        first_part = cleaned_name.split("-")[0].strip()
        second_part = cleaned_name.split("-")[-1].strip()

        if first_part:
            candidates.append(f"{first_part}, Polska")

        if second_part:
            candidates.append(f"{second_part}, Polska")

        candidates.append(f"{cleaned_name.replace('-', ' ')}, Polska")

    # Usuwamy duplikaty, zachowując kolejność.
    unique_candidates = []
    seen = set()

    for candidate in candidates:
        candidate_key = candidate.lower()

        if candidate_key not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate_key)

    return unique_candidates


def _get_imgw_stations_from_weather_measurements() -> pd.DataFrame:
    """
    Pobiera z bazy unikalne stacje IMGW z tabeli weather_measurements.
    """

    logger.info("Wczytuję unikalne stacje IMGW z tabeli weather_measurements.")

    try:
        with get_connection() as connection:
            df = connection.execute(
                """
                SELECT DISTINCT
                    weather_station_id,
                    imgw_station_id AS imgw_station_code,
                    station_name
                FROM weather_measurements
                WHERE source = 'IMGW'
                ORDER BY station_name;
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się odczytać stacji IMGW z bazy: %s", error)
        raise RuntimeError(
            "Nie udało się odczytać stacji IMGW z bazy. "
            "Najpierw upewnij się, że działało: python test_weather.py"
        ) from error

    if df.empty:
        raise ValueError(
            "Nie znaleziono stacji IMGW w tabeli weather_measurements. "
            "Najpierw uruchom: python test_weather.py"
        )

    logger.info("Wczytano unikalne stacje IMGW. Liczba stacji: %s", len(df))

    return df


def _geocode_single_station(
    station_name: str,
    geocode_function: RateLimiter,
    cache: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Geokoduje jedną stację IMGW po nazwie.

    Najpierw sprawdza cache, potem wykonuje zapytanie geokodujące.
    """

    station_key = _safe_text(station_name).upper()

    if station_key in cache:
        cached = cache[station_key]

        if (
            isinstance(cached, dict)
            and cached.get("latitude") is not None
            and cached.get("longitude") is not None
        ):
            logger.info("Stacja IMGW znaleziona w cache: %s", station_name)
            return cached

    queries = _generate_geocoding_queries(station_name)

    if not queries:
        logger.warning("Nie można utworzyć zapytania geokodującego dla stacji: %s", station_name)
        return None

    for query in queries:
        logger.info("Geokoduję stację IMGW. Stacja=%s, zapytanie=%s", station_name, query)

        location: Optional[Location] = geocode_function(
            query,
            exactly_one=True,
            country_codes="pl",
            addressdetails=True,
        )

        if location is None:
            logger.warning("Brak wyniku geokodowania dla zapytania: %s", query)
            continue

        latitude = float(location.latitude)
        longitude = float(location.longitude)

        if not _is_coordinate_in_poland(latitude, longitude):
            logger.warning(
                "Wynik geokodowania poza zakresem Polski. Stacja=%s, lat=%s, lon=%s",
                station_name,
                latitude,
                longitude,
            )
            continue

        result = {
            "station_name": station_name,
            "query": query,
            "latitude": latitude,
            "longitude": longitude,
            "geocoded_address": location.address,
            "geocoded_at": datetime.now().isoformat(),
        }

        cache[station_key] = result
        _save_geocoding_cache(cache)

        logger.info(
            "Stacja IMGW zgeokodowana poprawnie: %s -> lat=%s, lon=%s",
            station_name,
            latitude,
            longitude,
        )

        return result

    logger.warning("Nie udało się zgeokodować stacji IMGW: %s", station_name)

    return None


def geocode_imgw_stations() -> pd.DataFrame:
    """
    Geokoduje unikalne stacje IMGW z tabeli weather_measurements.
    """

    stations_df = _get_imgw_stations_from_weather_measurements()

    excluded_station_names = ["PLATFORMA"]

    before_exclusion = len(stations_df)

    stations_df = stations_df[
        ~stations_df["station_name"].astype(str).str.upper().isin(excluded_station_names)
    ].copy()

    removed_excluded = before_exclusion - len(stations_df)

    if removed_excluded > 0:
        logger.warning(
            "Usunięto stacje IMGW wykluczone z geokodowania przestrzennego: %s",
            removed_excluded,
        )

    geolocator = Nominatim(
        user_agent="internet_data_extraction_environmental_project"
    )

    geocode_function = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1,
        max_retries=2,
        error_wait_seconds=3,
        swallow_exceptions=True,
    )

    cache = _load_geocoding_cache()

    rows = []
    failed_stations = []

    for _, row in stations_df.iterrows():
        weather_station_id = _safe_text(row["weather_station_id"])
        imgw_station_code = _safe_text(row["imgw_station_code"])
        station_name = _safe_text(row["station_name"])

        geocoded = _geocode_single_station(
            station_name=station_name,
            geocode_function=geocode_function,
            cache=cache,
        )

        if geocoded is None:
            failed_stations.append(station_name)
            continue

        rows.append(
            {
                "weather_station_id": weather_station_id,
                "imgw_station_code": imgw_station_code,
                "imgw_station_code_9": pd.NA,
                "source": "IMGW_GEOCODED",
                "station_name": station_name,
                "station_type": "SYNOP",
                "data_from": pd.NaT,
                "data_to": pd.NaT,
                "is_active": True,
                "latitude": geocoded["latitude"],
                "longitude": geocoded["longitude"],
                "altitude_m": pd.NA,
                "downloaded_at": datetime.now(),
            }
        )

    if failed_stations:
        logger.warning("Nie udało się zgeokodować części stacji IMGW: %s", failed_stations)

    if not rows:
        raise ValueError("Nie udało się zgeokodować żadnej stacji IMGW.")

    output = pd.DataFrame(rows)

    output = output.drop_duplicates(subset=["weather_station_id"]).reset_index(drop=True)

    logger.info(
        "Geokodowanie stacji IMGW zakończone. Sukces: %s, błędy: %s",
        len(output),
        len(failed_stations),
    )

    return output


def save_imgw_geocoded_stations_csv(df: pd.DataFrame) -> Path:
    """
    Zapisuje zgeokodowane stacje IMGW do CSV.
    """

    if df is None or df.empty:
        raise ValueError("Nie można zapisać pustej tabeli zgeokodowanych stacji IMGW.")

    try:
        df.to_csv(IMGW_STATIONS_METADATA_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV ze stacjami IMGW: %s", error)
        raise RuntimeError(f"Nie udało się zapisać CSV: {IMGW_STATIONS_METADATA_CSV}") from error

    logger.info("Zapisano CSV ze stacjami IMGW: %s", IMGW_STATIONS_METADATA_CSV)

    return IMGW_STATIONS_METADATA_CSV


def run_imgw_station_geocoding() -> pd.DataFrame:
    """
    Pełny proces:
    - pobranie unikalnych stacji IMGW z bazy,
    - geokodowanie,
    - zapis CSV.
    """

    stations = geocode_imgw_stations()

    save_imgw_geocoded_stations_csv(stations)

    print(f"Liczba zgeokodowanych stacji IMGW: {len(stations)}")
    print("Kolumny tabeli stacji IMGW:")
    print(list(stations.columns))

    logger.info("Proces geokodowania stacji IMGW zakończony poprawnie.")

    return stations