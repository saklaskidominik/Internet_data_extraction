import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException, Timeout
from urllib3.util.retry import Retry

from src.config import (
    ESA_API_URL,
    ESA_MAX_PAGES,
    ESA_PAGE_DELAY_SECONDS,
    ESA_PROCESSED_CSV,
    RAW_ESA_DIR,
    REQUEST_TIMEOUT_SECONDS,
)
from src.utils import setup_logger


logger = setup_logger(__name__)


def _create_session() -> requests.Session:
    """
    Tworzy sesję requests z mechanizmem ponawiania zapytań.
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
            "Accept": "application/json",
        }
    )

    return session


def _request_esa_page(session: requests.Session, page: int = 1) -> dict[str, Any]:
    """
    Pobiera jedną stronę danych ESA.
    Obsługuje błędy HTTP, timeouty, błędy połączenia i niepoprawny JSON.
    """

    logger.info("Pobieram stronę ESA: %s", page)

    try:
        response = session.get(
            ESA_API_URL,
            params={"page": page},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    except Timeout as error:
        logger.error("Timeout podczas pobierania strony ESA %s: %s", page, error)
        raise RuntimeError(f"Przekroczono czas oczekiwania dla API ESA, strona {page}.") from error

    except HTTPError as error:
        status_code = error.response.status_code if error.response is not None else "brak"
        logger.error("Błąd HTTP ESA. Strona: %s. Status: %s. Szczegóły: %s", page, status_code, error)
        raise RuntimeError(f"API ESA zwróciło błąd HTTP {status_code} dla strony {page}.") from error

    except RequestException as error:
        logger.error("Błąd połączenia z API ESA. Strona: %s. Szczegóły: %s", page, error)
        raise RuntimeError(f"Nie udało się połączyć z API ESA dla strony {page}.") from error

    try:
        data = response.json()

    except ValueError as error:
        logger.error("Odpowiedź ESA nie jest poprawnym JSON-em. Strona: %s. Szczegóły: %s", page, error)
        raise RuntimeError(f"API ESA zwróciło niepoprawny JSON dla strony {page}.") from error

    if not data:
        logger.error("API ESA zwróciło pustą odpowiedź dla strony %s.", page)
        raise RuntimeError(f"API ESA zwróciło pustą odpowiedź dla strony {page}.")

    if not isinstance(data, dict):
        logger.error("Nieoczekiwany typ odpowiedzi ESA dla strony %s: %s", page, type(data))
        raise RuntimeError(f"API ESA zwróciło dane w nieoczekiwanym formacie dla strony {page}.")

    return data


def fetch_esa_data() -> dict[str, Any]:
    """
    Pobiera dane z ESA.

    Funkcja obsługuje paginację, jeśli API zwraca więcej niż jedną stronę.
    Wynikiem jest jeden słownik zawierający połączoną listę rekordów smog_data.
    """

    logger.info("Rozpoczynam pobieranie danych z ESA.")

    session = _create_session()

    first_page_data = _request_esa_page(session=session, page=1)

    if "smog_data" not in first_page_data:
        logger.error(
            "Brak klucza 'smog_data' w odpowiedzi ESA. Dostępne klucze: %s",
            list(first_page_data.keys()),
        )
        raise KeyError("Brak klucza 'smog_data' w odpowiedzi ESA.")

    all_records = first_page_data.get("smog_data", [])

    if not isinstance(all_records, list):
        logger.error("Pole 'smog_data' nie jest listą. Typ: %s", type(all_records))
        raise TypeError("Pole 'smog_data' w odpowiedzi ESA nie jest listą.")

    pages_total_raw = first_page_data.get("pages_total")

    if pages_total_raw in [None, "", "null"]:
        pages_total = 1
        logger.info("ESA nie zwróciła poprawnej wartości pages_total. Przyjmuję 1 stronę.")
    else:
        try:
            pages_total = int(pages_total_raw)
        except (TypeError, ValueError):
            pages_total = 1
            logger.info("Nie udało się odczytać pages_total jako liczby. Przyjmuję 1 stronę.")

    pages_total = max(1, min(pages_total, ESA_MAX_PAGES))

    logger.info("ESA pages_total: %s", pages_total)

    for page in range(2, pages_total + 1):
        time.sleep(ESA_PAGE_DELAY_SECONDS)

        page_data = _request_esa_page(session=session, page=page)
        page_records = page_data.get("smog_data", [])

        if not isinstance(page_records, list):
            logger.warning("Pomijam stronę %s, bo 'smog_data' nie jest listą.", page)
            continue

        all_records.extend(page_records)

    if len(all_records) == 0:
        logger.error("Nie pobrano żadnych rekordów ESA.")
        raise ValueError("Brak rekordów w danych ESA.")

    result = {
        "smog_data": all_records,
        "downloaded_pages": pages_total,
        "downloaded_records": len(all_records),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }

    logger.info("Dane ESA pobrano poprawnie. Liczba rekordów: %s", len(all_records))

    return result


def save_raw_esa_json(data: dict[str, Any]) -> Path:
    """
    Zapisuje surową odpowiedź JSON do folderu data/raw/esa.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RAW_ESA_DIR / f"esa_raw_{timestamp}.json"

    try:
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    except OSError as error:
        logger.error("Nie udało się zapisać surowego pliku ESA: %s", error)
        raise RuntimeError(f"Nie udało się zapisać pliku JSON ESA: {output_path}") from error

    logger.info("Zapisano surowy JSON ESA: %s", output_path)

    return output_path


def normalize_esa_data(data: dict[str, Any]) -> pd.DataFrame:
    """
    Zamienia JSON z ESA na płaską tabelę pandas.
    """

    logger.info("Rozpoczynam normalizację danych ESA.")

    if "smog_data" not in data:
        logger.error("Brak klucza 'smog_data' w odpowiedzi ESA. Dostępne klucze: %s", list(data.keys()))
        raise KeyError("Brak klucza 'smog_data' w odpowiedzi ESA.")

    records = data["smog_data"]

    if not isinstance(records, list):
        logger.error("Pole 'smog_data' nie jest listą. Typ: %s", type(records))
        raise TypeError("Pole 'smog_data' w odpowiedzi ESA nie jest listą.")

    if len(records) == 0:
        logger.error("Pole 'smog_data' jest puste.")
        raise ValueError("Brak rekordów w danych ESA.")

    try:
        df = pd.json_normalize(records)

    except Exception as error:
        logger.error("Błąd podczas normalizacji JSON ESA: %s", error)
        raise RuntimeError("Nie udało się zamienić danych ESA na tabelę.") from error

    df["downloaded_at"] = datetime.now()

    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed_duplicates = before - len(df)

    if removed_duplicates > 0:
        logger.warning("Usunięto duplikaty po normalizacji ESA: %s", removed_duplicates)

    if df.empty:
        logger.error("Po normalizacji tabela ESA jest pusta.")
        raise ValueError("Po normalizacji tabela ESA jest pusta.")

    logger.info("Normalizacja ESA zakończona. Liczba rekordów: %s", len(df))

    return df


def save_processed_esa_csv(df: pd.DataFrame) -> Path:
    """
    Zapisuje przetworzoną tabelę ESA do CSV.
    """

    if df is None or df.empty:
        logger.error("Próba zapisu pustej tabeli ESA do CSV.")
        raise ValueError("Nie można zapisać pustej tabeli ESA.")

    try:
        df.to_csv(ESA_PROCESSED_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV ESA: %s", error)
        raise RuntimeError(f"Nie udało się zapisać pliku CSV ESA: {ESA_PROCESSED_CSV}") from error

    logger.info("Zapisano przetworzone dane ESA do CSV: %s", ESA_PROCESSED_CSV)

    return ESA_PROCESSED_CSV


def run_esa_extraction() -> pd.DataFrame:
    """
    Pełny proces ESA:
    pobierz dane -> zapisz raw JSON -> przetwórz -> zapisz CSV.
    """

    data = fetch_esa_data()

    save_raw_esa_json(data)

    df = normalize_esa_data(data)

    save_processed_esa_csv(df)

    logger.info("Proces ESA zakończony poprawnie.")

    print(f"Liczba rekordów ESA: {len(df)}")
    print("Kolumny ESA:")
    print(list(df.columns))

    return df