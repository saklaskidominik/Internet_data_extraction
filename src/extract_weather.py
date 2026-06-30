import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException, Timeout
from urllib3.util.retry import Retry

from src.config import (
    IMGW_SYNOP_URL,
    IMGW_WEATHER_CSV,
    RAW_WEATHER_DIR,
    REQUEST_TIMEOUT_SECONDS,
)
from src.utils import setup_logger


logger = setup_logger(__name__)


def _create_session() -> requests.Session:
    """
    Tworzy sesję HTTP z mechanizmem ponawiania zapytań.
    Dzięki temu chwilowy błąd API nie przerywa od razu całego programu.
    """

    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update(
        {
            "User-Agent": "InternetDataExtractionProject/1.0",
            "Accept": "application/json, */*",
        }
    )

    return session


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


def _make_hash_id(prefix: str, *values: Any, length: int = 16) -> str:
    """
    Tworzy stabilny identyfikator na podstawie kilku pól.
    """

    text = "|".join(_safe_text(value) for value in values).lower()
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:length]

    return f"{prefix}_{digest}"


def fetch_imgw_weather() -> list[dict[str, Any]]:
    """
    Pobiera aktualne dane synoptyczne IMGW.

    Obsługiwane błędy:
    - timeout,
    - błąd HTTP,
    - błąd połączenia,
    - niepoprawny JSON,
    - pusta odpowiedź.
    """

    logger.info("Rozpoczynam pobieranie danych pogodowych IMGW.")

    session = _create_session()

    try:
        response = session.get(
            IMGW_SYNOP_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    except Timeout as error:
        logger.error("Timeout podczas pobierania danych IMGW: %s", error)
        raise RuntimeError("Przekroczono czas oczekiwania na odpowiedź API IMGW.") from error

    except HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "brak"
        response_text = error.response.text[:500] if error.response is not None else "brak treści odpowiedzi"

        logger.error(
            "Błąd HTTP IMGW. Status: %s. Fragment odpowiedzi: %s",
            status_code,
            response_text,
        )

        raise RuntimeError(
            f"API IMGW zwróciło błąd HTTP {status_code}. "
            f"Fragment odpowiedzi: {response_text}"
        ) from error

    except RequestException as error:
        logger.error("Błąd połączenia z API IMGW: %s", error)
        raise RuntimeError("Nie udało się połączyć z API IMGW.") from error

    try:
        data = response.json()

    except ValueError as error:
        response_text = response.text[:500] if response.text else "brak treści odpowiedzi"

        logger.error(
            "Odpowiedź IMGW nie jest poprawnym JSON-em. Content-Type=%s. Fragment odpowiedzi: %s",
            response.headers.get("Content-Type"),
            response_text,
        )

        raise RuntimeError(
            "API IMGW zwróciło odpowiedź, której nie da się odczytać jako JSON."
        ) from error

    if not data:
        logger.error("API IMGW zwróciło pustą odpowiedź.")
        raise ValueError("API IMGW zwróciło pustą odpowiedź.")

    if not isinstance(data, list):
        logger.error("Nieoczekiwany typ odpowiedzi IMGW: %s", type(data))
        raise TypeError("API IMGW powinno zwrócić listę rekordów JSON.")

    logger.info("Dane IMGW pobrano poprawnie. Liczba rekordów: %s", len(data))

    return data


def save_raw_imgw_weather_json(data: list[dict[str, Any]]) -> Path:
    """
    Zapisuje surowe dane IMGW do pliku JSON.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RAW_WEATHER_DIR / f"imgw_weather_raw_{timestamp}.json"

    try:
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    except OSError as error:
        logger.error("Nie udało się zapisać surowego JSON IMGW: %s", error)
        raise RuntimeError(f"Nie udało się zapisać pliku JSON IMGW: {output_path}") from error

    logger.info("Zapisano surowy JSON IMGW: %s", output_path)

    return output_path


def _to_numeric_series(series: pd.Series) -> pd.Series:
    """
    Konwertuje serię tekstową na liczbową.
    Obsługuje przecinek jako separator dziesiętny.
    """

    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False).str.strip(),
        errors="coerce",
    )


def normalize_imgw_weather(data: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Normalizuje dane pogodowe IMGW do jednej tabeli.

    Wynikowa tabela ma ujednolicone angielskie nazwy kolumn.
    """

    logger.info("Rozpoczynam normalizację danych pogodowych IMGW.")

    if not isinstance(data, list):
        raise TypeError("Dane IMGW muszą być listą słowników.")

    if len(data) == 0:
        raise ValueError("Lista danych IMGW jest pusta.")

    df = pd.json_normalize(data)

    if df.empty:
        raise ValueError("Po normalizacji tabela IMGW jest pusta.")

    logger.info("Kolumny IMGW po normalizacji: %s", list(df.columns))

    required_input_columns = [
        "id_stacji",
        "stacja",
        "data_pomiaru",
        "godzina_pomiaru",
        "temperatura",
        "predkosc_wiatru",
        "kierunek_wiatru",
        "wilgotnosc_wzgledna",
        "suma_opadu",
        "cisnienie",
    ]

    missing_columns = [
        column for column in required_input_columns
        if column not in df.columns
    ]

    if missing_columns:
        logger.warning(
            "Brakuje kolumn w danych IMGW: %s. Zostaną utworzone jako puste.",
            missing_columns,
        )

    for column in required_input_columns:
        if column not in df.columns:
            df[column] = pd.NA

    output = pd.DataFrame()

    output["imgw_station_id"] = df["id_stacji"].astype(str).str.strip()
    output["weather_station_id"] = "IMGW_" + output["imgw_station_id"]
    output["source"] = "IMGW"
    output["station_name"] = df["stacja"].astype(str).str.strip()

    output["measurement_date"] = df["data_pomiaru"].astype(str).str.strip()
    output["measurement_hour"] = df["godzina_pomiaru"].astype(str).str.strip()

    output["temperature"] = _to_numeric_series(df["temperatura"])
    output["wind_speed"] = _to_numeric_series(df["predkosc_wiatru"])
    output["wind_direction"] = _to_numeric_series(df["kierunek_wiatru"])
    output["relative_humidity"] = _to_numeric_series(df["wilgotnosc_wzgledna"])
    output["precipitation"] = _to_numeric_series(df["suma_opadu"])
    output["pressure"] = _to_numeric_series(df["cisnienie"])

    # IMGW zwraca datę i godzinę osobno. Łączymy je do jednego znacznika czasu.
    hour_numeric = pd.to_numeric(output["measurement_hour"], errors="coerce")

    output["measured_at"] = pd.to_datetime(
        output["measurement_date"] + " " + hour_numeric.fillna(0).astype(int).astype(str).str.zfill(2) + ":00:00",
        errors="coerce",
    )

    output["downloaded_at"] = datetime.now()

    # ID pomiaru: stacja + czas pomiaru.
    output["weather_measurement_id"] = output.apply(
        lambda row: _make_hash_id(
            "IMGW_MEAS",
            row["weather_station_id"],
            row["measured_at"],
        ),
        axis=1,
    )

    # Walidacja danych.
    invalid_time = output["measured_at"].isna().sum()

    if invalid_time > 0:
        logger.warning("Liczba rekordów IMGW z błędnym czasem pomiaru: %s", invalid_time)

    validation_ranges = {
        "temperature": (-50, 60),
        "wind_speed": (0, 100),
        "wind_direction": (0, 360),
        "relative_humidity": (0, 100),
        "precipitation": (0, 500),
        "pressure": (850, 1100),
    }

    for column, (min_value, max_value) in validation_ranges.items():
        invalid_mask = (
            output[column].notna()
            & ~output[column].between(min_value, max_value, inclusive="both")
        )

        invalid_count = invalid_mask.sum()

        if invalid_count > 0:
            logger.warning(
                "Kolumna IMGW %s ma wartości poza zakresem [%s, %s]. Liczba rekordów: %s",
                column,
                min_value,
                max_value,
                invalid_count,
            )
            output.loc[invalid_mask, column] = pd.NA

    before_drop = len(output)

    output = output.dropna(
        subset=[
            "weather_station_id",
            "station_name",
            "measured_at",
        ]
    ).copy()

    removed = before_drop - len(output)

    if removed > 0:
        logger.warning("Usunięto rekordy IMGW bez stacji lub czasu pomiaru: %s", removed)

    final_columns = [
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

    output = output[final_columns]

    before_duplicates = len(output)
    output = output.drop_duplicates(subset=["weather_measurement_id"]).reset_index(drop=True)
    removed_duplicates = before_duplicates - len(output)

    if removed_duplicates > 0:
        logger.warning("Usunięto duplikaty pomiarów IMGW: %s", removed_duplicates)

    if output.empty:
        logger.error("Po czyszczeniu tabela IMGW jest pusta.")
        raise ValueError("Po czyszczeniu tabela IMGW jest pusta.")

    logger.info("Normalizacja IMGW zakończona. Liczba rekordów: %s", len(output))

    return output


def save_imgw_weather_csv(df: pd.DataFrame) -> Path:
    """
    Zapisuje znormalizowane dane pogodowe IMGW do CSV.
    """

    if df is None or df.empty:
        logger.error("Próba zapisu pustej tabeli IMGW.")
        raise ValueError("Nie można zapisać pustej tabeli IMGW.")

    try:
        df.to_csv(IMGW_WEATHER_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV IMGW: %s", error)
        raise RuntimeError(f"Nie udało się zapisać CSV IMGW: {IMGW_WEATHER_CSV}") from error

    logger.info("Zapisano CSV IMGW: %s", IMGW_WEATHER_CSV)

    return IMGW_WEATHER_CSV


def run_imgw_weather_extraction() -> pd.DataFrame:
    """
    Pełny proces IMGW:
    pobierz dane -> zapisz raw JSON -> znormalizuj -> zapisz CSV.
    """

    data = fetch_imgw_weather()

    save_raw_imgw_weather_json(data)

    df = normalize_imgw_weather(data)

    save_imgw_weather_csv(df)

    logger.info("Proces pobierania danych pogodowych IMGW zakończony poprawnie.")

    print(f"Liczba rekordów IMGW: {len(df)}")
    print("Kolumny IMGW:")
    print(list(df.columns))

    return df