import hashlib
from typing import Tuple

import pandas as pd

from src.config import ESA_MEASUREMENTS_CSV, ESA_STATIONS_CSV
from src.utils import setup_logger


logger = setup_logger(__name__)


def _safe_text(value) -> str:
    """
    Zamienia wartość na bezpieczny tekst.
    Używane do tworzenia stabilnych identyfikatorów.
    """

    if pd.isna(value):
        return ""

    return str(value).strip()


def _make_hash_id(prefix: str, *values, length: int = 12) -> str:
    """
    Tworzy krótki stabilny identyfikator na podstawie kilku pól.

    ESA nie zwraca osobnego ID szkoły, dlatego ID tworzone jest
    na podstawie nazwy, adresu i współrzędnych.
    """

    text = "|".join(_safe_text(value) for value in values).lower()

    if not text.strip("|"):
        logger.warning("Tworzenie ID z pustych wartości. Prefix: %s", prefix)

    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:length]

    return f"{prefix}_{digest}"


def _check_required_input_columns(df: pd.DataFrame, expected_columns: list[str]) -> None:
    """
    Sprawdza, czy wejściowy DataFrame zawiera wymagane kolumny.
    Jeżeli kolumn brakuje, zapisuje ostrzeżenie w logach.
    """

    missing_columns = [column for column in expected_columns if column not in df.columns]

    if missing_columns:
        logger.warning(
            "Brakuje kolumn w danych ESA: %s. Zostaną utworzone jako puste.",
            missing_columns,
        )


def _validate_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Waliduje współrzędne geograficzne.
    Usuwa rekordy z błędnymi współrzędnymi.
    """

    before = len(df)

    df = df[
        df["latitude"].between(-90, 90, inclusive="both")
        & df["longitude"].between(-180, 180, inclusive="both")
    ].copy()

    removed = before - len(df)

    if removed > 0:
        logger.warning("Usunięto rekordy z błędnymi współrzędnymi: %s", removed)

    return df


def _validate_measurements(df: pd.DataFrame) -> pd.DataFrame:
    """
    Waliduje wartości pomiarowe.

    Błędne wartości nie usuwają całego rekordu.
    Są zamieniane na braki danych, żeby nie tracić lokalizacji i czasu pomiaru.
    """

    for column in ["pm10", "pm25", "humidity", "pressure"]:
        if column in df.columns:
            invalid_count = (df[column] < 0).sum()

            if invalid_count > 0:
                logger.warning(
                    "Kolumna %s zawiera wartości ujemne. Liczba błędnych rekordów: %s",
                    column,
                    invalid_count,
                )
                df.loc[df[column] < 0, column] = pd.NA

    if "humidity" in df.columns:
        invalid_humidity = (
            ~df["humidity"].between(0, 100, inclusive="both")
        ) & df["humidity"].notna()

        if invalid_humidity.sum() > 0:
            logger.warning(
                "Wilgotność poza zakresem 0-100%%. Liczba rekordów: %s",
                invalid_humidity.sum(),
            )
            df.loc[invalid_humidity, "humidity"] = pd.NA

    if "temperature" in df.columns:
        invalid_temperature = (
            ~df["temperature"].between(-50, 60, inclusive="both")
        ) & df["temperature"].notna()

        if invalid_temperature.sum() > 0:
            logger.warning(
                "Temperatura poza realistycznym zakresem -50 do 60 C. Liczba rekordów: %s",
                invalid_temperature.sum(),
            )
            df.loc[invalid_temperature, "temperature"] = pd.NA

    return df


def clean_esa_data(raw_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Czyści dane ESA i dzieli je na dwie tabele:

    1. stations:
       informacje o szkołach / punktach pomiarowych,

    2. measurements:
       pomiary jakości powietrza i parametrów meteorologicznych.

    Funkcja zawiera:
    - kontrolę pustych danych,
    - sprawdzenie brakujących kolumn,
    - konwersję typów danych,
    - walidację współrzędnych,
    - walidację wartości pomiarowych,
    - usuwanie duplikatów.
    """

    if raw_df is None:
        logger.error("Do clean_esa_data przekazano None zamiast DataFrame.")
        raise ValueError("Brak danych wejściowych ESA.")

    if not isinstance(raw_df, pd.DataFrame):
        logger.error("raw_df nie jest DataFrame. Typ: %s", type(raw_df))
        raise TypeError("Dane wejściowe ESA muszą być obiektem pandas DataFrame.")

    if raw_df.empty:
        logger.error("Przekazano pusty DataFrame ESA.")
        raise ValueError("Nie można czyścić pustej tabeli ESA.")

    logger.info("Rozpoczynam czyszczenie danych ESA. Liczba rekordów wejściowych: %s", len(raw_df))

    df = raw_df.copy()

    rename_map = {
        "timestamp": "measured_at",
        "school.name": "school_name",
        "school.street": "street",
        "school.post_code": "post_code",
        "school.city": "city",
        "school.longitude": "longitude",
        "school.latitude": "latitude",
        "data.humidity_avg": "humidity",
        "data.pressure_avg": "pressure",
        "data.temperature_avg": "temperature",
        "data.pm10_avg": "pm10",
        "data.pm25_avg": "pm25",
    }

    expected_input_columns = list(rename_map.keys()) + ["downloaded_at"]
    _check_required_input_columns(df, expected_input_columns)

    df = df.rename(columns=rename_map)

    required_columns = [
        "measured_at",
        "school_name",
        "street",
        "post_code",
        "city",
        "longitude",
        "latitude",
        "humidity",
        "pressure",
        "temperature",
        "pm10",
        "pm25",
        "downloaded_at",
    ]

    for column in required_columns:
        if column not in df.columns:
            df[column] = pd.NA

    df["measured_at"] = pd.to_datetime(df["measured_at"], errors="coerce")
    df["downloaded_at"] = pd.to_datetime(df["downloaded_at"], errors="coerce")

    missing_time = df["measured_at"].isna().sum()

    if missing_time > 0:
        logger.warning("Liczba rekordów bez poprawnego czasu pomiaru: %s", missing_time)

    numeric_columns = [
        "longitude",
        "latitude",
        "humidity",
        "pressure",
        "temperature",
        "pm10",
        "pm25",
    ]

    for column in numeric_columns:
        df[column] = (
            df[column]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df[column] = pd.to_numeric(df[column], errors="coerce")

    before_coordinates = len(df)
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    removed_coordinates = before_coordinates - len(df)

    if removed_coordinates > 0:
        logger.warning("Usunięto rekordy bez współrzędnych: %s", removed_coordinates)

    df = _validate_coordinates(df)
    df = _validate_measurements(df)

    df["source"] = "ESA"

    df["station_id"] = df.apply(
        lambda row: _make_hash_id(
            "ESA",
            row["school_name"],
            row["street"],
            row["post_code"],
            row["city"],
            row["latitude"],
            row["longitude"],
        ),
        axis=1,
    )

    df["measurement_id"] = df.apply(
        lambda row: _make_hash_id(
            "MEAS",
            row["station_id"],
            row["measured_at"],
        ),
        axis=1,
    )

    stations = df[
        [
            "station_id",
            "source",
            "school_name",
            "street",
            "post_code",
            "city",
            "latitude",
            "longitude",
        ]
    ].drop_duplicates(subset=["station_id"])

    stations = stations.sort_values(["city", "school_name"]).reset_index(drop=True)

    measurements = df[
        [
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
    ].drop_duplicates(subset=["measurement_id"])

    measurements = measurements.sort_values(["measured_at", "station_id"]).reset_index(drop=True)

    if stations.empty:
        logger.error("Po czyszczeniu tabela stations jest pusta.")
        raise ValueError("Po czyszczeniu nie uzyskano żadnych punktów pomiarowych ESA.")

    if measurements.empty:
        logger.error("Po czyszczeniu tabela measurements jest pusta.")
        raise ValueError("Po czyszczeniu nie uzyskano żadnych pomiarów ESA.")

    logger.info(
        "Czyszczenie ESA zakończone. Liczba stacji: %s, liczba pomiarów: %s",
        len(stations),
        len(measurements),
    )

    return stations, measurements


def save_esa_clean_tables(
    stations: pd.DataFrame,
    measurements: pd.DataFrame,
) -> Tuple[str, str]:
    """
    Zapisuje czyste tabele ESA do plików CSV.
    """

    if stations is None or stations.empty:
        logger.error("Próba zapisu pustej tabeli stations.")
        raise ValueError("Nie można zapisać pustej tabeli stations.")

    if measurements is None or measurements.empty:
        logger.error("Próba zapisu pustej tabeli measurements.")
        raise ValueError("Nie można zapisać pustej tabeli measurements.")

    try:
        stations.to_csv(ESA_STATIONS_CSV, index=False, encoding="utf-8-sig")
        measurements.to_csv(ESA_MEASUREMENTS_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Błąd zapisu czystych tabel ESA do CSV: %s", error)
        raise RuntimeError("Nie udało się zapisać czystych tabel ESA do plików CSV.") from error

    logger.info("Zapisano tabelę ESA stations: %s", ESA_STATIONS_CSV)
    logger.info("Zapisano tabelę ESA measurements: %s", ESA_MEASUREMENTS_CSV)

    return str(ESA_STATIONS_CSV), str(ESA_MEASUREMENTS_CSV)