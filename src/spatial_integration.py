from typing import Tuple

import numpy as np
import pandas as pd

from src.config import (
    ESA_GIOS_NEAREST_CSV,
    POLAND_MAX_LAT,
    POLAND_MAX_LON,
    POLAND_MIN_LAT,
    POLAND_MIN_LON,
)
from src.database import get_connection
from src.utils import setup_logger


logger = setup_logger(__name__)


def _validate_stations_dataframe(
    df: pd.DataFrame,
    required_columns: list[str],
    dataframe_name: str,
) -> None:
    """
    Sprawdza, czy DataFrame istnieje, nie jest pusty i zawiera wymagane kolumny.
    """

    if df is None:
        logger.error("%s jest None.", dataframe_name)
        raise ValueError(f"{dataframe_name} nie istnieje.")

    if not isinstance(df, pd.DataFrame):
        logger.error("%s nie jest obiektem pandas DataFrame.", dataframe_name)
        raise TypeError(f"{dataframe_name} musi być pandas DataFrame.")

    if df.empty:
        logger.error("%s jest pusty.", dataframe_name)
        raise ValueError(f"{dataframe_name} jest pusty.")

    missing_columns = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        logger.error(
            "W %s brakuje kolumn: %s",
            dataframe_name,
            missing_columns,
        )
        raise ValueError(f"W {dataframe_name} brakuje kolumn: {missing_columns}")


def load_esa_stations_from_database() -> pd.DataFrame:
    """
    Wczytuje punkty/szkoły ESA z tabeli stations w bazie DuckDB.
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
                WHERE source = 'ESA'
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się wczytać stacji ESA z bazy: %s", error)
        raise RuntimeError("Nie udało się wczytać stacji ESA z bazy danych.") from error

    required_columns = [
        "esa_station_id",
        "school_name",
        "esa_city",
        "esa_latitude",
        "esa_longitude",
    ]

    _validate_stations_dataframe(df, required_columns, "esa_stations")

    logger.info("Wczytano stacje ESA z bazy. Liczba rekordów: %s", len(df))

    return df

def _filter_points_to_poland_bounds(
    df: pd.DataFrame,
    latitude_column: str,
    longitude_column: str,
    dataframe_name: str,
) -> pd.DataFrame:
    """
    Zostawia tylko punkty znajdujące się w przybliżonym zakresie współrzędnych Polski.

    Dzięki temu odrzucamy błędne lub testowe punkty, które mają współrzędne
    daleko poza Polską i zaburzają analizę odległości.
    """

    before = len(df)

    filtered = df[
        df[latitude_column].between(POLAND_MIN_LAT, POLAND_MAX_LAT, inclusive="both")
        & df[longitude_column].between(POLAND_MIN_LON, POLAND_MAX_LON, inclusive="both")
    ].copy()

    removed = before - len(filtered)

    if removed > 0:
        logger.warning(
            "Usunięto punkty spoza przybliżonego zakresu Polski z %s: %s",
            dataframe_name,
            removed,
        )

    return filtered


def load_gios_stations_from_database() -> pd.DataFrame:
    """
    Wczytuje stacje GIOŚ z tabeli gios_stations w bazie DuckDB.
    """

    logger.info("Wczytuję stacje GIOŚ z bazy danych.")

    try:
        with get_connection() as connection:
            df = connection.execute(
                """
                SELECT
                    station_id AS gios_station_id,
                    gios_station_id AS gios_original_station_id,
                    station_name AS gios_station_name,
                    city AS gios_city,
                    commune AS gios_commune,
                    district AS gios_district,
                    province AS gios_province,
                    address_street AS gios_address_street,
                    latitude AS gios_latitude,
                    longitude AS gios_longitude
                FROM gios_stations
                """
            ).fetchdf()

    except Exception as error:
        logger.error("Nie udało się wczytać stacji GIOŚ z bazy: %s", error)
        raise RuntimeError("Nie udało się wczytać stacji GIOŚ z bazy danych.") from error

    required_columns = [
        "gios_station_id",
        "gios_station_name",
        "gios_city",
        "gios_province",
        "gios_latitude",
        "gios_longitude",
    ]

    _validate_stations_dataframe(df, required_columns, "gios_stations")

    logger.info("Wczytano stacje GIOŚ z bazy. Liczba rekordów: %s", len(df))

    return df


def _haversine_distance_km(
    lat1: np.ndarray,
    lon1: np.ndarray,
    lat2: np.ndarray,
    lon2: np.ndarray,
) -> np.ndarray:
    """
    Liczy odległość po powierzchni Ziemi między punktami WGS84.

    Wynik jest w kilometrach.
    """

    earth_radius_km = 6371.0088

    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon / 2.0) ** 2
    )

    c = 2 * np.arcsin(np.sqrt(a))

    return earth_radius_km * c


def find_nearest_gios_station(
    esa_stations: pd.DataFrame,
    gios_stations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Dla każdej szkoły/stacji ESA znajduje najbliższą stację GIOŚ.

    Metoda:
    - dla każdego punktu ESA liczymy odległość do wszystkich stacji GIOŚ,
    - wybieramy stację GIOŚ z najmniejszą odległością.
    """

    logger.info("Rozpoczynam dopasowanie najbliższych stacji GIOŚ do punktów ESA.")

    _validate_stations_dataframe(
        esa_stations,
        ["esa_station_id", "school_name", "esa_latitude", "esa_longitude"],
        "esa_stations",
    )

    _validate_stations_dataframe(
        gios_stations,
        ["gios_station_id", "gios_station_name", "gios_latitude", "gios_longitude"],
        "gios_stations",
    )

    esa = esa_stations.copy()
    gios = gios_stations.copy()

        # Usuwamy rekordy testowe z ESA, jeżeli występują w danych źródłowych.
    test_school_mask = (
        esa["school_name"].astype(str).str.upper().str.contains("TEST", na=False)
        | esa["esa_city"].astype(str).str.upper().str.contains("TEST", na=False)
    )

    removed_test_records = test_school_mask.sum()

    if removed_test_records > 0:
        logger.warning("Usunięto testowe rekordy ESA: %s", removed_test_records)

    esa = esa[~test_school_mask].copy()

    numeric_columns_esa = ["esa_latitude", "esa_longitude"]
    numeric_columns_gios = ["gios_latitude", "gios_longitude"]

    for column in numeric_columns_esa:
        esa[column] = pd.to_numeric(esa[column], errors="coerce")

    for column in numeric_columns_gios:
        gios[column] = pd.to_numeric(gios[column], errors="coerce")

    before_esa = len(esa)
    esa = esa.dropna(subset=numeric_columns_esa).copy()
    removed_esa = before_esa - len(esa)

    if removed_esa > 0:
        logger.warning("Usunięto punkty ESA bez poprawnych współrzędnych: %s", removed_esa)

    before_gios = len(gios)
    gios = gios.dropna(subset=numeric_columns_gios).copy()
    removed_gios = before_gios - len(gios)

    if removed_gios > 0:
        logger.warning("Usunięto stacje GIOŚ bez poprawnych współrzędnych: %s", removed_gios)
    
        esa = _filter_points_to_poland_bounds(
        df=esa,
        latitude_column="esa_latitude",
        longitude_column="esa_longitude",
        dataframe_name="esa_stations",
    )

    gios = _filter_points_to_poland_bounds(
        df=gios,
        latitude_column="gios_latitude",
        longitude_column="gios_longitude",
        dataframe_name="gios_stations",
    )

    if esa.empty:
        raise ValueError("Brak punktów ESA po usunięciu błędnych współrzędnych.")

    if gios.empty:
        raise ValueError("Brak stacji GIOŚ po usunięciu błędnych współrzędnych.")

    gios_latitudes = gios["gios_latitude"].to_numpy()
    gios_longitudes = gios["gios_longitude"].to_numpy()

    nearest_rows = []

    for _, esa_row in esa.iterrows():
        distances = _haversine_distance_km(
            lat1=np.array([esa_row["esa_latitude"]]),
            lon1=np.array([esa_row["esa_longitude"]]),
            lat2=gios_latitudes,
            lon2=gios_longitudes,
        )

        nearest_index = int(np.argmin(distances))
        nearest_distance = float(distances[nearest_index])
        nearest_gios = gios.iloc[nearest_index]

        nearest_rows.append(
            {
                "esa_station_id": esa_row["esa_station_id"],
                "school_name": esa_row["school_name"],
                "esa_city": esa_row.get("esa_city"),
                "esa_street": esa_row.get("esa_street"),
                "esa_post_code": esa_row.get("esa_post_code"),
                "esa_latitude": esa_row["esa_latitude"],
                "esa_longitude": esa_row["esa_longitude"],
                "nearest_gios_station_id": nearest_gios["gios_station_id"],
                "nearest_gios_original_station_id": nearest_gios.get("gios_original_station_id"),
                "nearest_gios_station_name": nearest_gios["gios_station_name"],
                "gios_city": nearest_gios.get("gios_city"),
                "gios_commune": nearest_gios.get("gios_commune"),
                "gios_district": nearest_gios.get("gios_district"),
                "gios_province": nearest_gios.get("gios_province"),
                "gios_address_street": nearest_gios.get("gios_address_street"),
                "gios_latitude": nearest_gios["gios_latitude"],
                "gios_longitude": nearest_gios["gios_longitude"],
                "distance_km": round(nearest_distance, 3),
            }
        )

    result = pd.DataFrame(nearest_rows)

    if result.empty:
        logger.error("Tabela dopasowania ESA-GIOŚ jest pusta.")
        raise ValueError("Nie udało się utworzyć tabeli dopasowania ESA-GIOŚ.")

    result = result.sort_values("distance_km").reset_index(drop=True)

    logger.info(
        "Dopasowanie ESA-GIOŚ zakończone. Liczba rekordów: %s. Średnia odległość: %.3f km.",
        len(result),
        result["distance_km"].mean(),
    )

    return result


def save_esa_gios_nearest_csv(df: pd.DataFrame) -> str:
    """
    Zapisuje tabelę najbliższych stacji GIOŚ dla punktów ESA do CSV.
    """

    if df is None or df.empty:
        logger.error("Próba zapisu pustej tabeli ESA-GIOŚ.")
        raise ValueError("Nie można zapisać pustej tabeli ESA-GIOŚ.")

    try:
        df.to_csv(ESA_GIOS_NEAREST_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV ESA-GIOŚ: %s", error)
        raise RuntimeError("Nie udało się zapisać tabeli ESA-GIOŚ do CSV.") from error

    logger.info("Zapisano tabelę ESA-GIOŚ do CSV: %s", ESA_GIOS_NEAREST_CSV)

    return str(ESA_GIOS_NEAREST_CSV)


def run_esa_gios_spatial_integration() -> pd.DataFrame:
    """
    Pełny proces integracji przestrzennej:
    - wczytaj stacje ESA z bazy,
    - wczytaj stacje GIOŚ z bazy,
    - znajdź najbliższą stację GIOŚ dla każdej szkoły ESA,
    - zapisz wynik do CSV.
    """

    esa_stations = load_esa_stations_from_database()
    gios_stations = load_gios_stations_from_database()

    nearest_df = find_nearest_gios_station(
        esa_stations=esa_stations,
        gios_stations=gios_stations,
    )

    save_esa_gios_nearest_csv(nearest_df)

    print(f"Liczba dopasowanych punktów ESA do GIOŚ: {len(nearest_df)}")
    print("Kolumny tabeli ESA-GIOŚ:")
    print(list(nearest_df.columns))

    return nearest_df