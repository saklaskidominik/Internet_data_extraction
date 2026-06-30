import numpy as np
import pandas as pd

from src.config import (
    ESA_IMGW_NEAREST_CSV,
    POLAND_MAX_LAT,
    POLAND_MAX_LON,
    POLAND_MIN_LAT,
    POLAND_MIN_LON,
)
from src.database import get_connection
from src.utils import setup_logger


logger = setup_logger(__name__)


def _haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2_array: np.ndarray,
    lon2_array: np.ndarray,
) -> np.ndarray:
    """
    Oblicza odległość haversine między jednym punktem a wieloma punktami.
    Wynik jest w kilometrach.
    """

    earth_radius_km = 6371.0

    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2_array)
    lon2_rad = np.radians(lon2_array)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(delta_lon / 2) ** 2
    )

    c = 2 * np.arcsin(np.sqrt(a))

    return earth_radius_km * c


def _filter_poland_bounds(
    df: pd.DataFrame,
    latitude_column: str,
    longitude_column: str,
    dataframe_name: str,
) -> pd.DataFrame:
    """
    Zostawia tylko punkty znajdujące się w przybliżonym zakresie Polski.
    """

    before = len(df)

    filtered = df[
        df[latitude_column].between(POLAND_MIN_LAT, POLAND_MAX_LAT, inclusive="both")
        & df[longitude_column].between(POLAND_MIN_LON, POLAND_MAX_LON, inclusive="both")
    ].copy()

    removed = before - len(filtered)

    if removed > 0:
        logger.warning(
            "Usunięto punkty spoza zakresu Polski z %s: %s",
            dataframe_name,
            removed,
        )

    return filtered


def _load_esa_stations() -> pd.DataFrame:
    """
    Wczytuje stacje ESA z tabeli stations.
    """

    logger.info("Wczytuję stacje ESA z bazy danych.")

    try:
        with get_connection() as connection:
            df = connection.execute(
                """
                SELECT
                    station_id AS esa_station_id,
                    school_name,
                    city AS esa_city,
                    street AS esa_street,
                    post_code AS esa_post_code,
                    latitude AS esa_latitude,
                    longitude AS esa_longitude
                FROM stations
                WHERE source = 'ESA';
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się wczytać stacji ESA z bazy: %s", error)
        raise RuntimeError("Nie udało się wczytać stacji ESA z bazy danych.") from error

    if df.empty:
        raise ValueError("Tabela stacji ESA jest pusta.")

    logger.info("Wczytano stacje ESA. Liczba rekordów: %s", len(df))

    return df


def _load_imgw_stations_with_latest_weather() -> pd.DataFrame:
    """
    Wczytuje stacje IMGW razem z najnowszym dostępnym pomiarem pogodowym.
    """

    logger.info("Wczytuję stacje IMGW z najnowszą pogodą z bazy danych.")

    try:
        with get_connection() as connection:
            df = connection.execute(
                """
                WITH latest_weather AS (
                    SELECT *
                    FROM weather_measurements
                    QUALIFY ROW_NUMBER() OVER (
                        PARTITION BY weather_station_id
                        ORDER BY measured_at DESC
                    ) = 1
                )
                SELECT
                    s.weather_station_id AS imgw_weather_station_id,
                    s.imgw_station_code,
                    s.station_name AS imgw_station_name,
                    s.latitude AS imgw_latitude,
                    s.longitude AS imgw_longitude,
                    w.measured_at AS weather_measured_at,
                    w.temperature AS imgw_temperature,
                    w.wind_speed AS imgw_wind_speed,
                    w.wind_direction AS imgw_wind_direction,
                    w.relative_humidity AS imgw_relative_humidity,
                    w.precipitation AS imgw_precipitation,
                    w.pressure AS imgw_pressure
                FROM imgw_weather_stations s
                LEFT JOIN latest_weather w
                    ON s.weather_station_id = w.weather_station_id
                WHERE s.is_active = TRUE;
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się wczytać stacji IMGW z pogodą: %s", error)
        raise RuntimeError(
            "Nie udało się wczytać stacji IMGW z pogodą. "
            "Upewnij się, że wcześniej działały: python test_weather.py oraz python test_imgw_geocoding.py"
        ) from error

    if df.empty:
        raise ValueError("Tabela stacji IMGW z pogodą jest pusta.")

    logger.info("Wczytano stacje IMGW z pogodą. Liczba rekordów: %s", len(df))

    return df


def integrate_esa_with_nearest_imgw_weather() -> pd.DataFrame:
    """
    Dla każdej stacji ESA znajduje najbliższą stację IMGW
    i dołącza najnowsze dane pogodowe z tej stacji.
    """

    esa = _load_esa_stations()
    imgw = _load_imgw_stations_with_latest_weather()

    logger.info("Rozpoczynam integrację ESA z najbliższą stacją IMGW.")

    test_mask = (
        esa["school_name"].astype(str).str.upper().str.contains("TEST", na=False)
        | esa["esa_city"].astype(str).str.upper().str.contains("TEST", na=False)
    )

    removed_test = int(test_mask.sum())

    if removed_test > 0:
        logger.warning("Usunięto testowe rekordy ESA: %s", removed_test)

    esa = esa[~test_mask].copy()

    esa["esa_latitude"] = pd.to_numeric(esa["esa_latitude"], errors="coerce")
    esa["esa_longitude"] = pd.to_numeric(esa["esa_longitude"], errors="coerce")
    imgw["imgw_latitude"] = pd.to_numeric(imgw["imgw_latitude"], errors="coerce")
    imgw["imgw_longitude"] = pd.to_numeric(imgw["imgw_longitude"], errors="coerce")

    esa = esa.dropna(subset=["esa_latitude", "esa_longitude"]).copy()
    imgw = imgw.dropna(subset=["imgw_latitude", "imgw_longitude"]).copy()

    esa = _filter_poland_bounds(
        esa,
        latitude_column="esa_latitude",
        longitude_column="esa_longitude",
        dataframe_name="ESA",
    )

    imgw = _filter_poland_bounds(
        imgw,
        latitude_column="imgw_latitude",
        longitude_column="imgw_longitude",
        dataframe_name="IMGW",
    )

    if esa.empty:
        raise ValueError("Brak poprawnych punktów ESA po walidacji.")

    if imgw.empty:
        raise ValueError("Brak poprawnych stacji IMGW po walidacji.")

    imgw_latitudes = imgw["imgw_latitude"].to_numpy()
    imgw_longitudes = imgw["imgw_longitude"].to_numpy()

    rows = []

    for _, esa_row in esa.iterrows():
        distances = _haversine_distance_km(
            lat1=esa_row["esa_latitude"],
            lon1=esa_row["esa_longitude"],
            lat2_array=imgw_latitudes,
            lon2_array=imgw_longitudes,
        )

        nearest_index = int(np.argmin(distances))
        nearest_imgw = imgw.iloc[nearest_index]
        nearest_distance = round(float(distances[nearest_index]), 3)

        rows.append(
            {
                "esa_station_id": esa_row["esa_station_id"],
                "school_name": esa_row["school_name"],
                "esa_city": esa_row["esa_city"],
                "esa_street": esa_row["esa_street"],
                "esa_post_code": esa_row["esa_post_code"],
                "esa_latitude": esa_row["esa_latitude"],
                "esa_longitude": esa_row["esa_longitude"],
                "nearest_imgw_station_id": nearest_imgw["imgw_weather_station_id"],
                "nearest_imgw_station_code": nearest_imgw["imgw_station_code"],
                "nearest_imgw_station_name": nearest_imgw["imgw_station_name"],
                "imgw_latitude": nearest_imgw["imgw_latitude"],
                "imgw_longitude": nearest_imgw["imgw_longitude"],
                "distance_to_imgw_km": nearest_distance,
                "weather_measured_at": nearest_imgw["weather_measured_at"],
                "imgw_temperature": nearest_imgw["imgw_temperature"],
                "imgw_wind_speed": nearest_imgw["imgw_wind_speed"],
                "imgw_wind_direction": nearest_imgw["imgw_wind_direction"],
                "imgw_relative_humidity": nearest_imgw["imgw_relative_humidity"],
                "imgw_precipitation": nearest_imgw["imgw_precipitation"],
                "imgw_pressure": nearest_imgw["imgw_pressure"],
            }
        )

    result = pd.DataFrame(rows)

    result = result.sort_values("distance_to_imgw_km").reset_index(drop=True)

    if result.empty:
        raise ValueError("Po integracji ESA-IMGW tabela wynikowa jest pusta.")

    logger.info(
        "Integracja ESA-IMGW zakończona. Liczba rekordów: %s. Średnia odległość: %.3f km.",
        len(result),
        result["distance_to_imgw_km"].mean(),
    )

    return result


def save_esa_imgw_weather_csv(df: pd.DataFrame) -> str:
    """
    Zapisuje wynik integracji ESA-IMGW do CSV.
    """

    if df is None or df.empty:
        raise ValueError("Nie można zapisać pustej tabeli ESA-IMGW.")

    try:
        df.to_csv(ESA_IMGW_NEAREST_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV ESA-IMGW: %s", error)
        raise RuntimeError(f"Nie udało się zapisać CSV ESA-IMGW: {ESA_IMGW_NEAREST_CSV}") from error

    logger.info("Zapisano CSV ESA-IMGW: %s", ESA_IMGW_NEAREST_CSV)

    return str(ESA_IMGW_NEAREST_CSV)


def run_esa_imgw_weather_integration() -> pd.DataFrame:
    """
    Pełny proces integracji:
    ESA -> najbliższa stacja IMGW -> aktualna pogoda.
    """

    integrated_df = integrate_esa_with_nearest_imgw_weather()

    save_esa_imgw_weather_csv(integrated_df)

    print(f"Liczba rekordów ESA-IMGW: {len(integrated_df)}")
    print("Kolumny tabeli ESA-IMGW:")
    print(list(integrated_df.columns))

    logger.info("Proces integracji ESA-IMGW zakończony poprawnie.")

    return integrated_df