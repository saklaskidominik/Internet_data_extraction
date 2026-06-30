from typing import Tuple

import duckdb
import pandas as pd

from src.config import DATABASE_PATH
from src.utils import setup_logger


logger = setup_logger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Tworzy połączenie z lokalną bazą DuckDB.

    Baza jest zapisywana w pliku:
    data/database/environmental_data.duckdb
    """

    try:
        connection = duckdb.connect(str(DATABASE_PATH))

    except Exception as error:
        logger.error("Nie udało się połączyć z bazą DuckDB: %s", error)
        raise RuntimeError(f"Nie udało się połączyć z bazą danych: {DATABASE_PATH}") from error

    return connection


def initialize_database() -> None:
    """
    Tworzy tabele w bazie danych, jeżeli jeszcze nie istnieją.
    """

    logger.info("Inicjalizuję bazę danych DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    station_id VARCHAR PRIMARY KEY,
                    source VARCHAR,
                    school_name VARCHAR,
                    street VARCHAR,
                    post_code VARCHAR,
                    city VARCHAR,
                    latitude DOUBLE,
                    longitude DOUBLE
                );
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS air_measurements (
                    measurement_id VARCHAR PRIMARY KEY,
                    station_id VARCHAR,
                    source VARCHAR,
                    measured_at TIMESTAMP,
                    downloaded_at TIMESTAMP,
                    pm10 DOUBLE,
                    pm25 DOUBLE,
                    temperature DOUBLE,
                    humidity DOUBLE,
                    pressure DOUBLE
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji bazy danych: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować bazy danych.") from error

    logger.info("Baza danych została zainicjalizowana poprawnie.")


def insert_stations(stations: pd.DataFrame) -> int:
    """
    Dopisuje nowe stacje ESA do tabeli stations.

    Funkcja nie dubluje rekordów:
    jeżeli station_id już istnieje w bazie, rekord jest pomijany.
    """

    if stations is None or stations.empty:
        logger.warning("Tabela stations jest pusta. Nie zapisuję nic do bazy.")
        return 0

    required_columns = [
        "station_id",
        "source",
        "school_name",
        "street",
        "post_code",
        "city",
        "latitude",
        "longitude",
    ]

    missing_columns = [column for column in required_columns if column not in stations.columns]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli stations: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli stations: {missing_columns}")

    stations_to_insert = stations[required_columns].copy()

    try:
        with get_connection() as connection:
            before_count = connection.execute(
                "SELECT COUNT(*) FROM stations"
            ).fetchone()[0]

            connection.register("stations_df", stations_to_insert)

            connection.execute(
                """
                INSERT INTO stations
                SELECT *
                FROM stations_df
                WHERE station_id NOT IN (
                    SELECT station_id FROM stations
                );
                """
            )

            after_count = connection.execute(
                "SELECT COUNT(*) FROM stations"
            ).fetchone()[0]

            inserted_count = after_count - before_count

    except Exception as error:
        logger.error("Błąd podczas zapisu stacji do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać stacji do bazy danych.") from error

    logger.info("Zapisano nowe stacje do bazy: %s", inserted_count)

    return inserted_count


def insert_air_measurements(measurements: pd.DataFrame) -> int:
    """
    Dopisuje nowe pomiary ESA do tabeli air_measurements.

    Funkcja nie dubluje rekordów:
    jeżeli measurement_id już istnieje w bazie, rekord jest pomijany.
    """

    if measurements is None or measurements.empty:
        logger.warning("Tabela measurements jest pusta. Nie zapisuję nic do bazy.")
        return 0

    required_columns = [
        "measurement_id",
        "station_id",
        "source",
        "measured_at",
        "downloaded_at",
        "pm10",
        "pm25",
        "temperature",
        "humidity",
        "pressure",
    ]

    missing_columns = [column for column in required_columns if column not in measurements.columns]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli measurements: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli measurements: {missing_columns}")

    measurements_to_insert = measurements[required_columns].copy()

    try:
        with get_connection() as connection:
            before_count = connection.execute(
                "SELECT COUNT(*) FROM air_measurements"
            ).fetchone()[0]

            connection.register("measurements_df", measurements_to_insert)

            connection.execute(
                """
                INSERT INTO air_measurements
                SELECT *
                FROM measurements_df
                WHERE measurement_id NOT IN (
                    SELECT measurement_id FROM air_measurements
                );
                """
            )

            after_count = connection.execute(
                "SELECT COUNT(*) FROM air_measurements"
            ).fetchone()[0]

            inserted_count = after_count - before_count

    except Exception as error:
        logger.error("Błąd podczas zapisu pomiarów do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać pomiarów do bazy danych.") from error

    logger.info("Zapisano nowe pomiary do bazy: %s", inserted_count)

    return inserted_count


def save_esa_to_database(
    stations: pd.DataFrame,
    measurements: pd.DataFrame,
) -> Tuple[int, int]:
    """
    Pełny zapis ESA do bazy:
    - inicjalizacja tabel,
    - zapis stacji,
    - zapis pomiarów.
    """

    initialize_database()

    inserted_stations = insert_stations(stations)
    inserted_measurements = insert_air_measurements(measurements)

    return inserted_stations, inserted_measurements


def get_database_summary() -> dict:
    """
    Zwraca krótkie podsumowanie zawartości bazy.
    Przydatne do sprawdzenia, czy dane faktycznie się zapisują.
    """

    try:
        with get_connection() as connection:
            stations_count = connection.execute(
                "SELECT COUNT(*) FROM stations"
            ).fetchone()[0]

            measurements_count = connection.execute(
                "SELECT COUNT(*) FROM air_measurements"
            ).fetchone()[0]

            min_time, max_time = connection.execute(
                """
                SELECT 
                    MIN(measured_at),
                    MAX(measured_at)
                FROM air_measurements
                """
            ).fetchone()

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania bazy: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania bazy danych.") from error

    return {
        "stations_count": stations_count,
        "measurements_count": measurements_count,
        "min_measured_at": min_time,
        "max_measured_at": max_time,
    }

def initialize_gios_tables() -> None:
    """
    Tworzy tabelę gios_stations w bazie DuckDB, jeżeli jeszcze nie istnieje.
    """

    logger.info("Inicjalizuję tabelę gios_stations w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gios_stations (
                    station_id VARCHAR PRIMARY KEY,
                    gios_station_id VARCHAR,
                    source VARCHAR,
                    station_name VARCHAR,
                    city VARCHAR,
                    commune VARCHAR,
                    district VARCHAR,
                    province VARCHAR,
                    address_street VARCHAR,
                    latitude DOUBLE,
                    longitude DOUBLE,
                    downloaded_at TIMESTAMP
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji tabeli gios_stations: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować tabeli gios_stations.") from error

    logger.info("Tabela gios_stations została zainicjalizowana poprawnie.")


def insert_gios_stations(gios_stations: pd.DataFrame) -> int:
    """
    Dopisuje stacje GIOŚ do tabeli gios_stations.

    Funkcja nie dubluje rekordów:
    jeżeli station_id już istnieje w bazie, rekord jest pomijany.
    """

    if gios_stations is None or gios_stations.empty:
        logger.warning("Tabela gios_stations jest pusta. Nie zapisuję nic do bazy.")
        return 0

    required_columns = [
        "station_id",
        "gios_station_id",
        "source",
        "station_name",
        "city",
        "commune",
        "district",
        "province",
        "address_street",
        "latitude",
        "longitude",
        "downloaded_at",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in gios_stations.columns
    ]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli gios_stations: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli gios_stations: {missing_columns}")

    gios_stations_to_insert = gios_stations[required_columns].copy()

    try:
        with get_connection() as connection:
            initialize_gios_tables()

            before_count = connection.execute(
                "SELECT COUNT(*) FROM gios_stations"
            ).fetchone()[0]

            connection.register("gios_stations_df", gios_stations_to_insert)

            connection.execute(
                """
                INSERT INTO gios_stations
                SELECT *
                FROM gios_stations_df
                WHERE station_id NOT IN (
                    SELECT station_id FROM gios_stations
                );
                """
            )

            after_count = connection.execute(
                "SELECT COUNT(*) FROM gios_stations"
            ).fetchone()[0]

            inserted_count = after_count - before_count

    except Exception as error:
        logger.error("Błąd podczas zapisu stacji GIOŚ do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać stacji GIOŚ do bazy danych.") from error

    logger.info("Zapisano nowe stacje GIOŚ do bazy: %s", inserted_count)

    return inserted_count


def save_gios_stations_to_database(gios_stations: pd.DataFrame) -> int:
    """
    Pełny zapis stacji GIOŚ do bazy:
    - inicjalizacja tabeli,
    - zapis nowych rekordów.
    """

    initialize_gios_tables()
    inserted_gios_stations = insert_gios_stations(gios_stations)

    return inserted_gios_stations


def get_gios_database_summary() -> dict:
    """
    Zwraca krótkie podsumowanie tabeli gios_stations.
    """

    initialize_gios_tables()

    try:
        with get_connection() as connection:
            gios_stations_count = connection.execute(
                "SELECT COUNT(*) FROM gios_stations"
            ).fetchone()[0]

            province_count = connection.execute(
                """
                SELECT COUNT(DISTINCT province)
                FROM gios_stations
                WHERE province IS NOT NULL
                """
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania GIOŚ z bazy: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania GIOŚ z bazy danych.") from error

    return {
        "gios_stations_count": gios_stations_count,
        "province_count": province_count,
    }

def initialize_esa_gios_nearest_table() -> None:
    """
    Tworzy tabelę esa_gios_nearest_stations w bazie DuckDB,
    jeżeli jeszcze nie istnieje.
    """

    logger.info("Inicjalizuję tabelę esa_gios_nearest_stations w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS esa_gios_nearest_stations (
                    esa_station_id VARCHAR PRIMARY KEY,
                    school_name VARCHAR,
                    esa_city VARCHAR,
                    esa_street VARCHAR,
                    esa_post_code VARCHAR,
                    esa_latitude DOUBLE,
                    esa_longitude DOUBLE,
                    nearest_gios_station_id VARCHAR,
                    nearest_gios_original_station_id VARCHAR,
                    nearest_gios_station_name VARCHAR,
                    gios_city VARCHAR,
                    gios_commune VARCHAR,
                    gios_district VARCHAR,
                    gios_province VARCHAR,
                    gios_address_street VARCHAR,
                    gios_latitude DOUBLE,
                    gios_longitude DOUBLE,
                    distance_km DOUBLE
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji tabeli ESA-GIOŚ: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować tabeli ESA-GIOŚ.") from error

    logger.info("Tabela esa_gios_nearest_stations została zainicjalizowana poprawnie.")


def insert_esa_gios_nearest(nearest_df: pd.DataFrame) -> int:
    """
    Zapisuje wynik integracji ESA-GIOŚ do tabeli esa_gios_nearest_stations.

    Tabela jest odświeżana przy każdym zapisie, ponieważ dopasowanie
    najbliższej stacji GIOŚ jest tabelą referencyjną, a nie pomiarem czasowym.
    """

    if nearest_df is None or nearest_df.empty:
        logger.error("Tabela ESA-GIOŚ jest pusta. Nie zapisuję nic do bazy.")
        raise ValueError("Nie można zapisać pustej tabeli ESA-GIOŚ do bazy.")

    required_columns = [
        "esa_station_id",
        "school_name",
        "esa_city",
        "esa_street",
        "esa_post_code",
        "esa_latitude",
        "esa_longitude",
        "nearest_gios_station_id",
        "nearest_gios_original_station_id",
        "nearest_gios_station_name",
        "gios_city",
        "gios_commune",
        "gios_district",
        "gios_province",
        "gios_address_street",
        "gios_latitude",
        "gios_longitude",
        "distance_km",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in nearest_df.columns
    ]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli ESA-GIOŚ: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli ESA-GIOŚ: {missing_columns}")

    nearest_to_insert = nearest_df[required_columns].copy()

    try:
        with get_connection() as connection:
            connection.register("esa_gios_nearest_df", nearest_to_insert)

            connection.execute("DELETE FROM esa_gios_nearest_stations;")

            connection.execute(
                """
                INSERT INTO esa_gios_nearest_stations
                SELECT *
                FROM esa_gios_nearest_df;
                """
            )

            inserted_count = connection.execute(
                "SELECT COUNT(*) FROM esa_gios_nearest_stations"
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas zapisu tabeli ESA-GIOŚ do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać tabeli ESA-GIOŚ do bazy danych.") from error

    logger.info("Zapisano rekordy ESA-GIOŚ do bazy: %s", inserted_count)

    return inserted_count


def save_esa_gios_nearest_to_database(nearest_df: pd.DataFrame) -> int:
    """
    Pełny zapis integracji ESA-GIOŚ do bazy:
    - inicjalizacja tabeli,
    - odświeżenie danych w tabeli.
    """

    initialize_esa_gios_nearest_table()
    inserted_count = insert_esa_gios_nearest(nearest_df)

    return inserted_count


def get_esa_gios_nearest_summary() -> dict:
    """
    Zwraca podsumowanie tabeli esa_gios_nearest_stations.
    """

    initialize_esa_gios_nearest_table()

    try:
        with get_connection() as connection:
            total_count = connection.execute(
                "SELECT COUNT(*) FROM esa_gios_nearest_stations"
            ).fetchone()[0]

            min_distance, avg_distance, max_distance = connection.execute(
                """
                SELECT
                    MIN(distance_km),
                    AVG(distance_km),
                    MAX(distance_km)
                FROM esa_gios_nearest_stations
                """
            ).fetchone()

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania ESA-GIOŚ z bazy: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania ESA-GIOŚ z bazy danych.") from error

    return {
        "total_count": total_count,
        "min_distance_km": min_distance,
        "avg_distance_km": avg_distance,
        "max_distance_km": max_distance,
    }

def initialize_weather_tables() -> None:
    """
    Tworzy tabelę weather_measurements w bazie DuckDB,
    jeżeli jeszcze nie istnieje.
    """

    logger.info("Inicjalizuję tabelę weather_measurements w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_measurements (
                    weather_measurement_id VARCHAR PRIMARY KEY,
                    weather_station_id VARCHAR,
                    imgw_station_id VARCHAR,
                    source VARCHAR,
                    station_name VARCHAR,
                    measured_at TIMESTAMP,
                    downloaded_at TIMESTAMP,
                    temperature DOUBLE,
                    wind_speed DOUBLE,
                    wind_direction DOUBLE,
                    relative_humidity DOUBLE,
                    precipitation DOUBLE,
                    pressure DOUBLE
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji tabeli weather_measurements: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować tabeli weather_measurements.") from error

    logger.info("Tabela weather_measurements została zainicjalizowana poprawnie.")


def insert_weather_measurements(weather_df: pd.DataFrame) -> int:
    """
    Dopisuje dane pogodowe IMGW do tabeli weather_measurements.

    Funkcja nie dubluje rekordów:
    jeżeli weather_measurement_id już istnieje w bazie, rekord jest pomijany.
    """

    if weather_df is None or weather_df.empty:
        logger.warning("Tabela weather_df jest pusta. Nie zapisuję nic do bazy.")
        return 0

    required_columns = [
        "weather_measurement_id",
        "weather_station_id",
        "imgw_station_id",
        "source",
        "station_name",
        "measured_at",
        "downloaded_at",
        "temperature",
        "wind_speed",
        "wind_direction",
        "relative_humidity",
        "precipitation",
        "pressure",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in weather_df.columns
    ]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli weather_df: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli weather_df: {missing_columns}")

    weather_to_insert = weather_df[required_columns].copy()

    try:
        with get_connection() as connection:
            before_count = connection.execute(
                "SELECT COUNT(*) FROM weather_measurements"
            ).fetchone()[0]

            connection.register("weather_df", weather_to_insert)

            connection.execute(
                """
                INSERT INTO weather_measurements
                SELECT *
                FROM weather_df
                WHERE weather_measurement_id NOT IN (
                    SELECT weather_measurement_id FROM weather_measurements
                );
                """
            )

            after_count = connection.execute(
                "SELECT COUNT(*) FROM weather_measurements"
            ).fetchone()[0]

            inserted_count = after_count - before_count

    except Exception as error:
        logger.error("Błąd podczas zapisu danych pogodowych IMGW do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać danych pogodowych IMGW do bazy.") from error

    logger.info("Zapisano nowe pomiary pogodowe IMGW do bazy: %s", inserted_count)

    return inserted_count


def save_weather_to_database(weather_df: pd.DataFrame) -> int:
    """
    Pełny zapis danych pogodowych IMGW do bazy:
    - inicjalizacja tabeli,
    - zapis nowych rekordów.
    """

    initialize_weather_tables()
    inserted_count = insert_weather_measurements(weather_df)

    return inserted_count


def get_weather_database_summary() -> dict:
    """
    Zwraca podsumowanie tabeli weather_measurements.
    """

    initialize_weather_tables()

    try:
        with get_connection() as connection:
            total_count = connection.execute(
                "SELECT COUNT(*) FROM weather_measurements"
            ).fetchone()[0]

            station_count = connection.execute(
                """
                SELECT COUNT(DISTINCT weather_station_id)
                FROM weather_measurements
                """
            ).fetchone()[0]

            min_time, max_time = connection.execute(
                """
                SELECT
                    MIN(measured_at),
                    MAX(measured_at)
                FROM weather_measurements
                """
            ).fetchone()

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania IMGW z bazy: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania IMGW z bazy danych.") from error

    return {
        "total_count": total_count,
        "station_count": station_count,
        "min_measured_at": min_time,
        "max_measured_at": max_time,
    }

def initialize_imgw_station_metadata_table() -> None:
    """
    Tworzy tabelę imgw_weather_stations w bazie DuckDB,
    jeżeli jeszcze nie istnieje.
    """

    logger.info("Inicjalizuję tabelę imgw_weather_stations w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS imgw_weather_stations (
                    weather_station_id VARCHAR PRIMARY KEY,
                    imgw_station_code VARCHAR,
                    imgw_station_code_9 VARCHAR,
                    source VARCHAR,
                    station_name VARCHAR,
                    station_type VARCHAR,
                    data_from TIMESTAMP,
                    data_to TIMESTAMP,
                    is_active BOOLEAN,
                    latitude DOUBLE,
                    longitude DOUBLE,
                    altitude_m DOUBLE,
                    downloaded_at TIMESTAMP
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji tabeli imgw_weather_stations: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować tabeli imgw_weather_stations.") from error

    logger.info("Tabela imgw_weather_stations została zainicjalizowana poprawnie.")


def insert_imgw_station_metadata(metadata_df: pd.DataFrame) -> int:
    """
    Zapisuje metadane stacji IMGW do tabeli imgw_weather_stations.

    Tabela jest odświeżana przy każdym zapisie, bo metadane są tabelą referencyjną.
    """

    if metadata_df is None or metadata_df.empty:
        logger.error("Tabela metadanych IMGW jest pusta. Nie zapisuję nic do bazy.")
        raise ValueError("Nie można zapisać pustych metadanych IMGW do bazy.")

    required_columns = [
        "weather_station_id",
        "imgw_station_code",
        "imgw_station_code_9",
        "source",
        "station_name",
        "station_type",
        "data_from",
        "data_to",
        "is_active",
        "latitude",
        "longitude",
        "altitude_m",
        "downloaded_at",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in metadata_df.columns
    ]

    if missing_columns:
        logger.error("Brakuje kolumn w metadanych IMGW: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w metadanych IMGW: {missing_columns}")

    metadata_to_insert = metadata_df[required_columns].copy()

    try:
        with get_connection() as connection:
            connection.register("imgw_metadata_df", metadata_to_insert)

            connection.execute("DELETE FROM imgw_weather_stations;")

            connection.execute(
                """
                INSERT INTO imgw_weather_stations
                SELECT *
                FROM imgw_metadata_df;
                """
            )

            inserted_count = connection.execute(
                "SELECT COUNT(*) FROM imgw_weather_stations"
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas zapisu metadanych IMGW do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać metadanych IMGW do bazy.") from error

    logger.info("Zapisano metadane stacji IMGW do bazy: %s", inserted_count)

    return inserted_count


def save_imgw_station_metadata_to_database(metadata_df: pd.DataFrame) -> int:
    """
    Pełny zapis metadanych IMGW do bazy:
    - inicjalizacja tabeli,
    - odświeżenie danych.
    """

    initialize_imgw_station_metadata_table()
    inserted_count = insert_imgw_station_metadata(metadata_df)

    return inserted_count


def get_imgw_station_metadata_summary() -> dict:
    """
    Zwraca podsumowanie tabeli imgw_weather_stations.
    """

    initialize_imgw_station_metadata_table()

    try:
        with get_connection() as connection:
            total_count = connection.execute(
                "SELECT COUNT(*) FROM imgw_weather_stations"
            ).fetchone()[0]

            active_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM imgw_weather_stations
                WHERE is_active = TRUE
                """
            ).fetchone()[0]

            min_lat, max_lat, min_lon, max_lon = connection.execute(
                """
                SELECT
                    MIN(latitude),
                    MAX(latitude),
                    MIN(longitude),
                    MAX(longitude)
                FROM imgw_weather_stations
                """
            ).fetchone()

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania metadanych IMGW: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania metadanych IMGW.") from error

    return {
        "total_count": total_count,
        "active_count": active_count,
        "min_latitude": min_lat,
        "max_latitude": max_lat,
        "min_longitude": min_lon,
        "max_longitude": max_lon,
    }

def initialize_esa_imgw_weather_table() -> None:
    """
    Tworzy tabelę esa_imgw_nearest_weather w bazie DuckDB,
    jeżeli jeszcze nie istnieje.
    """

    logger.info("Inicjalizuję tabelę esa_imgw_nearest_weather w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS esa_imgw_nearest_weather (
                    esa_station_id VARCHAR PRIMARY KEY,
                    school_name VARCHAR,
                    esa_city VARCHAR,
                    esa_street VARCHAR,
                    esa_post_code VARCHAR,
                    esa_latitude DOUBLE,
                    esa_longitude DOUBLE,
                    nearest_imgw_station_id VARCHAR,
                    nearest_imgw_station_code VARCHAR,
                    nearest_imgw_station_name VARCHAR,
                    imgw_latitude DOUBLE,
                    imgw_longitude DOUBLE,
                    distance_to_imgw_km DOUBLE,
                    weather_measured_at TIMESTAMP,
                    imgw_temperature DOUBLE,
                    imgw_wind_speed DOUBLE,
                    imgw_wind_direction DOUBLE,
                    imgw_relative_humidity DOUBLE,
                    imgw_precipitation DOUBLE,
                    imgw_pressure DOUBLE
                );
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji tabeli ESA-IMGW: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować tabeli ESA-IMGW.") from error

    logger.info("Tabela esa_imgw_nearest_weather została zainicjalizowana poprawnie.")


def insert_esa_imgw_weather(integrated_df: pd.DataFrame) -> int:
    """
    Zapisuje wynik integracji ESA-IMGW do bazy.

    Tabela jest odświeżana przy każdym uruchomieniu,
    bo zawiera aktualny snapshot pogody przypisany do punktów ESA.
    """

    if integrated_df is None or integrated_df.empty:
        logger.error("Tabela ESA-IMGW jest pusta. Nie zapisuję nic do bazy.")
        raise ValueError("Nie można zapisać pustej tabeli ESA-IMGW do bazy.")

    required_columns = [
        "esa_station_id",
        "school_name",
        "esa_city",
        "esa_street",
        "esa_post_code",
        "esa_latitude",
        "esa_longitude",
        "nearest_imgw_station_id",
        "nearest_imgw_station_code",
        "nearest_imgw_station_name",
        "imgw_latitude",
        "imgw_longitude",
        "distance_to_imgw_km",
        "weather_measured_at",
        "imgw_temperature",
        "imgw_wind_speed",
        "imgw_wind_direction",
        "imgw_relative_humidity",
        "imgw_precipitation",
        "imgw_pressure",
    ]

    missing_columns = [
        column for column in required_columns
        if column not in integrated_df.columns
    ]

    if missing_columns:
        logger.error("Brakuje kolumn w tabeli ESA-IMGW: %s", missing_columns)
        raise ValueError(f"Brakuje kolumn w tabeli ESA-IMGW: {missing_columns}")

    data_to_insert = integrated_df[required_columns].copy()

    try:
        with get_connection() as connection:
            connection.register("esa_imgw_df", data_to_insert)

            connection.execute("DELETE FROM esa_imgw_nearest_weather;")

            connection.execute(
                """
                INSERT INTO esa_imgw_nearest_weather
                SELECT *
                FROM esa_imgw_df;
                """
            )

            inserted_count = connection.execute(
                "SELECT COUNT(*) FROM esa_imgw_nearest_weather"
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas zapisu ESA-IMGW do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać ESA-IMGW do bazy danych.") from error

    logger.info("Zapisano rekordy ESA-IMGW do bazy: %s", inserted_count)

    return inserted_count


def save_esa_imgw_weather_to_database(integrated_df: pd.DataFrame) -> int:
    """
    Pełny zapis integracji ESA-IMGW do bazy.
    """

    initialize_esa_imgw_weather_table()
    inserted_count = insert_esa_imgw_weather(integrated_df)

    return inserted_count


def get_esa_imgw_weather_summary() -> dict:
    """
    Zwraca podsumowanie tabeli esa_imgw_nearest_weather.
    """

    initialize_esa_imgw_weather_table()

    try:
        with get_connection() as connection:
            total_count = connection.execute(
                "SELECT COUNT(*) FROM esa_imgw_nearest_weather"
            ).fetchone()[0]

            min_distance, avg_distance, max_distance = connection.execute(
                """
                SELECT
                    MIN(distance_to_imgw_km),
                    AVG(distance_to_imgw_km),
                    MAX(distance_to_imgw_km)
                FROM esa_imgw_nearest_weather
                """
            ).fetchone()

            station_count = connection.execute(
                """
                SELECT COUNT(DISTINCT nearest_imgw_station_id)
                FROM esa_imgw_nearest_weather
                """
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania ESA-IMGW: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania ESA-IMGW.") from error

    return {
        "total_count": total_count,
        "nearest_imgw_station_count": station_count,
        "min_distance_km": min_distance,
        "avg_distance_km": avg_distance,
        "max_distance_km": max_distance,
    }

def initialize_environmental_snapshot_table() -> None:
    """
    Tworzy tabelę environmental_snapshot w bazie DuckDB.
    """

    logger.info("Inicjalizuję tabelę environmental_snapshot w bazie DuckDB.")

    try:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS environmental_snapshot AS
                SELECT *
                FROM (
                    SELECT 1 AS placeholder
                )
                WHERE FALSE;
                """
            )

    except Exception as error:
        logger.error("Błąd podczas inicjalizacji environmental_snapshot: %s", error)
        raise RuntimeError("Nie udało się zainicjalizować environmental_snapshot.") from error

    logger.info("Tabela environmental_snapshot została zainicjalizowana poprawnie.")


def save_environmental_snapshot_to_database(snapshot_df: pd.DataFrame) -> int:
    """
    Zapisuje finalny zbiór environmental_snapshot do bazy.

    Tabela jest odświeżana w całości, bo jest finalnym snapshotem analitycznym.
    """

    if snapshot_df is None or snapshot_df.empty:
        logger.error("Finalny zbiór environmental_snapshot jest pusty.")
        raise ValueError("Nie można zapisać pustego environmental_snapshot do bazy.")

    try:
        with get_connection() as connection:
            connection.execute("DROP TABLE IF EXISTS environmental_snapshot;")

            connection.register("snapshot_df", snapshot_df)

            connection.execute(
                """
                CREATE TABLE environmental_snapshot AS
                SELECT *
                FROM snapshot_df;
                """
            )

            inserted_count = connection.execute(
                "SELECT COUNT(*) FROM environmental_snapshot"
            ).fetchone()[0]

    except Exception as error:
        logger.error("Błąd podczas zapisu environmental_snapshot do bazy: %s", error)
        raise RuntimeError("Nie udało się zapisać environmental_snapshot do bazy.") from error

    logger.info("Zapisano environmental_snapshot do bazy. Liczba rekordów: %s", inserted_count)

    return inserted_count


def get_environmental_snapshot_summary() -> dict:
    """
    Zwraca podsumowanie finalnego zbioru environmental_snapshot.
    """

    try:
        with get_connection() as connection:
            total_count = connection.execute(
                "SELECT COUNT(*) FROM environmental_snapshot"
            ).fetchone()[0]

            city_count = connection.execute(
                "SELECT COUNT(DISTINCT esa_city) FROM environmental_snapshot"
            ).fetchone()[0]

            avg_pm10, avg_pm25 = connection.execute(
                """
                SELECT
                    AVG(pm10),
                    AVG(pm25)
                FROM environmental_snapshot
                """
            ).fetchone()

            avg_gios_distance, avg_imgw_distance = connection.execute(
                """
                SELECT
                    AVG(distance_to_gios_km),
                    AVG(distance_to_imgw_km)
                FROM environmental_snapshot
                """
            ).fetchone()

    except Exception as error:
        logger.error("Błąd podczas odczytu podsumowania environmental_snapshot: %s", error)
        raise RuntimeError("Nie udało się odczytać podsumowania environmental_snapshot.") from error

    return {
        "total_count": total_count,
        "city_count": city_count,
        "avg_pm10": avg_pm10,
        "avg_pm25": avg_pm25,
        "avg_distance_to_gios_km": avg_gios_distance,
        "avg_distance_to_imgw_km": avg_imgw_distance,
    }