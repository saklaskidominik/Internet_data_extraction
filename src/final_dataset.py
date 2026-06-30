import pandas as pd

from src.config import ENVIRONMENTAL_SNAPSHOT_CSV
from src.database import get_connection
from src.utils import setup_logger


logger = setup_logger(__name__)


def build_environmental_snapshot() -> pd.DataFrame:
    """
    Buduje finalny zbiór analityczny projektu.

    Zbiór łączy:
    - najnowsze pomiary ESA,
    - dane stacji ESA,
    - najbliższą stację GIOŚ,
    - najbliższą stację IMGW,
    - aktualne dane pogodowe IMGW.
    """

    logger.info("Rozpoczynam budowę finalnego zbioru environmental_snapshot.")

    try:
        with get_connection() as connection:
            df = connection.execute(
                """
                WITH latest_esa_measurements AS (
                    SELECT *
                    FROM air_measurements
                    QUALIFY ROW_NUMBER() OVER (
                        PARTITION BY station_id
                        ORDER BY measured_at DESC
                    ) = 1
                )
                SELECT
                    s.station_id AS esa_station_id,
                    s.school_name,
                    s.city AS esa_city,
                    s.street AS esa_street,
                    s.post_code AS esa_post_code,
                    s.latitude AS esa_latitude,
                    s.longitude AS esa_longitude,

                    m.measured_at AS esa_measured_at,
                    m.downloaded_at AS esa_downloaded_at,
                    m.pm10,
                    m.pm25,
                    m.temperature AS esa_temperature,
                    m.humidity AS esa_humidity,
                    m.pressure AS esa_pressure,

                    g.nearest_gios_station_id,
                    g.nearest_gios_original_station_id,
                    g.nearest_gios_station_name,
                    g.gios_city,
                    g.gios_commune,
                    g.gios_district,
                    g.gios_province,
                    g.gios_latitude,
                    g.gios_longitude,
                    g.distance_km AS distance_to_gios_km,

                    w.nearest_imgw_station_id,
                    w.nearest_imgw_station_code,
                    w.nearest_imgw_station_name,
                    w.imgw_latitude,
                    w.imgw_longitude,
                    w.distance_to_imgw_km,
                    w.weather_measured_at,
                    w.imgw_temperature,
                    w.imgw_wind_speed,
                    w.imgw_wind_direction,
                    w.imgw_relative_humidity,
                    w.imgw_precipitation,
                    w.imgw_pressure

                FROM stations s

                LEFT JOIN latest_esa_measurements m
                    ON s.station_id = m.station_id

                LEFT JOIN esa_gios_nearest_stations g
                    ON s.station_id = g.esa_station_id

                LEFT JOIN esa_imgw_nearest_weather w
                    ON s.station_id = w.esa_station_id

                WHERE s.source = 'ESA'
                  AND UPPER(COALESCE(s.school_name, '')) NOT LIKE '%TEST%'
                  AND UPPER(COALESCE(s.city, '')) NOT LIKE '%TEST%';
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się zbudować environmental_snapshot: %s", error)
        raise RuntimeError(
            "Nie udało się zbudować finalnego zbioru danych. "
            "Upewnij się, że wcześniej działały integracje ESA-GIOŚ i ESA-IMGW."
        ) from error

    if df.empty:
        raise ValueError("Finalny zbiór environmental_snapshot jest pusty.")

    before_drop = len(df)

    df = df.dropna(
        subset=[
            "esa_station_id",
            "esa_latitude",
            "esa_longitude",
        ]
    ).copy()

    removed = before_drop - len(df)

    if removed > 0:
        logger.warning(
            "Usunięto rekordy z finalnego zbioru bez podstawowych danych lokalizacyjnych: %s",
            removed,
        )

    numeric_columns = [
        "pm10",
        "pm25",
        "esa_temperature",
        "esa_humidity",
        "esa_pressure",
        "distance_to_gios_km",
        "distance_to_imgw_km",
        "imgw_temperature",
        "imgw_wind_speed",
        "imgw_wind_direction",
        "imgw_relative_humidity",
        "imgw_precipitation",
        "imgw_pressure",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.sort_values(["esa_city", "school_name"]).reset_index(drop=True)

    logger.info(
        "Finalny zbiór environmental_snapshot utworzony. Liczba rekordów: %s",
        len(df),
    )

    return df


def save_environmental_snapshot_csv(df: pd.DataFrame) -> str:
    """
    Zapisuje finalny zbiór do CSV.
    """

    if df is None or df.empty:
        raise ValueError("Nie można zapisać pustego environmental_snapshot.")

    try:
        df.to_csv(ENVIRONMENTAL_SNAPSHOT_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać environmental_snapshot do CSV: %s", error)
        raise RuntimeError(
            f"Nie udało się zapisać CSV: {ENVIRONMENTAL_SNAPSHOT_CSV}"
        ) from error

    logger.info("Zapisano environmental_snapshot do CSV: %s", ENVIRONMENTAL_SNAPSHOT_CSV)

    return str(ENVIRONMENTAL_SNAPSHOT_CSV)


def run_environmental_snapshot_build() -> pd.DataFrame:
    """
    Pełny proces:
    - budowa finalnego zbioru,
    - zapis CSV.
    """

    snapshot = build_environmental_snapshot()

    save_environmental_snapshot_csv(snapshot)

    print(f"Liczba rekordów finalnego zbioru: {len(snapshot)}")
    print("Kolumny finalnego zbioru:")
    print(list(snapshot.columns))

    logger.info("Proces budowy finalnego zbioru zakończony poprawnie.")

    return snapshot