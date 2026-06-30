import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException, Timeout
from urllib3.util.retry import Retry

from src.config import (
    GIOS_MAX_PAGES,
    GIOS_PAGE_DELAY_SECONDS,
    GIOS_PAGE_SIZE,
    GIOS_STATIONS_CSV,
    GIOS_STATIONS_URL,
    RAW_GIOS_DIR,
    REQUEST_TIMEOUT_SECONDS,
)
from src.utils import setup_logger


logger = setup_logger(__name__)


def _create_session() -> requests.Session:
    """
    Tworzy sesję HTTP z obsługą ponawiania zapytań.

    Dla API GIOŚ ustawiamy Accept: */*, ponieważ przy zbyt sztywnym
    nagłówku Accept endpoint może zwracać HTTP 406 Not Acceptable.
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
            "Accept": "*/*",
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


def _make_hash_id(prefix: str, *values: Any, length: int = 12) -> str:
    """
    Tworzy awaryjne ID, gdyby API nie zwróciło identyfikatora stacji.
    """

    text = "|".join(_safe_text(value) for value in values).lower()
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:length]

    return f"{prefix}_{digest}"


def _try_parse_json_response(response: requests.Response, page: int) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Próbuje odczytać odpowiedź HTTP jako JSON.
    Jeżeli się nie uda, zapisuje w logach Content-Type i fragment treści odpowiedzi.
    """

    try:
        data = response.json()

    except ValueError as error:
        response_text = response.text[:500] if response.text else "brak treści odpowiedzi"

        logger.error(
            "Odpowiedź GIOŚ nie jest poprawnym JSON-em. Page=%s. Content-Type=%s. Fragment odpowiedzi: %s",
            page,
            response.headers.get("Content-Type"),
            response_text,
        )

        raise RuntimeError(
            f"API GIOŚ zwróciło odpowiedź, której nie da się odczytać jako JSON. "
            f"Page={page}. Fragment odpowiedzi: {response_text}"
        ) from error

    if not isinstance(data, (dict, list)):
        logger.error("Nieoczekiwany typ odpowiedzi GIOŚ. Page=%s. Typ: %s", page, type(data))
        raise RuntimeError(f"API GIOŚ zwróciło dane w nieoczekiwanym formacie. Page={page}.")

    return data


def _send_gios_request(
    session: requests.Session,
    page: int,
    size: int,
    use_params: bool = True,
    accept_header: Optional[str] = "*/*",
) -> requests.Response:
    """
    Wysyła pojedyncze zapytanie do API GIOŚ.

    Parametr use_params pozwala wykonać zapytanie:
    - z page/size,
    - bez page/size.

    To zwiększa odporność kodu, bo niektóre endpointy API zwracają całą listę
    bez potrzeby paginacji.
    """

    params = {"page": page, "size": size} if use_params else None

    headers = {
        "User-Agent": "InternetDataExtractionProject/1.0",
    }

    if accept_header is not None:
        headers["Accept"] = accept_header

    return session.get(
        GIOS_STATIONS_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _request_gios_stations_page(
    session: requests.Session,
    page: int,
    size: int,
) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Pobiera jedną stronę listy stacji GIOŚ.

    Funkcja obsługuje:
    - timeout,
    - błąd połączenia,
    - błędy HTTP,
    - HTTP 406 przez ponowienie zapytania różnymi wariantami nagłówków,
    - niepoprawny JSON.
    """

    logger.info("Pobieram stronę stacji GIOŚ: page=%s, size=%s", page, size)

    request_variants = [
        {
            "use_params": True,
            "accept_header": "*/*",
            "description": "z page/size oraz Accept */*",
        },
        {
            "use_params": True,
            "accept_header": None,
            "description": "z page/size bez nagłówka Accept",
        },
        {
            "use_params": False,
            "accept_header": "*/*",
            "description": "bez page/size oraz Accept */*",
        },
        {
            "use_params": False,
            "accept_header": None,
            "description": "bez page/size i bez nagłówka Accept",
        },
    ]

    last_error: Optional[Exception] = None
    last_response_text = ""

    for variant in request_variants:
        try:
            logger.info("Próba pobrania GIOŚ: %s", variant["description"])

            response = _send_gios_request(
                session=session,
                page=page,
                size=size,
                use_params=variant["use_params"],
                accept_header=variant["accept_header"],
            )

            if response.status_code == 406:
                last_response_text = response.text[:500] if response.text else "brak treści odpowiedzi"

                logger.warning(
                    "GIOŚ zwrócił HTTP 406 dla wariantu: %s. Fragment odpowiedzi: %s",
                    variant["description"],
                    last_response_text,
                )

                continue

            response.raise_for_status()

            data = _try_parse_json_response(response=response, page=page)

            logger.info("Pobrano dane GIOŚ poprawnie dla wariantu: %s", variant["description"])

            return data

        except Timeout as error:
            logger.error("Timeout podczas pobierania stacji GIOŚ. Page=%s. Błąd: %s", page, error)
            raise RuntimeError(f"Przekroczono czas oczekiwania dla API GIOŚ, page={page}.") from error

        except HTTPError as error:
            last_error = error

            status_code = error.response.status_code if error.response is not None else "brak"
            response_text = error.response.text[:500] if error.response is not None else "brak treści odpowiedzi"

            logger.warning(
                "Błąd HTTP GIOŚ dla wariantu: %s. Page=%s. Status=%s. Fragment odpowiedzi: %s",
                variant["description"],
                page,
                status_code,
                response_text,
            )

            last_response_text = response_text
            continue

        except RequestException as error:
            logger.error("Błąd połączenia z API GIOŚ. Page=%s. Szczegóły: %s", page, error)
            raise RuntimeError(f"Nie udało się połączyć z API GIOŚ, page={page}.") from error

    logger.error(
        "Nie udało się pobrać danych GIOŚ po sprawdzeniu kilku wariantów zapytania. "
        "Ostatni fragment odpowiedzi: %s",
        last_response_text,
    )

    if last_error is not None:
        raise RuntimeError(
            f"API GIOŚ nie zwróciło poprawnej odpowiedzi. Page={page}. "
            f"Ostatni fragment odpowiedzi: {last_response_text}"
        ) from last_error

    raise RuntimeError(
        f"API GIOŚ nie zwróciło poprawnej odpowiedzi. Page={page}. "
        f"Ostatni fragment odpowiedzi: {last_response_text}"
    )


def _looks_like_station_list(value: Any) -> bool:
    """
    Sprawdza, czy dana wartość wygląda jak lista stacji.
    """

    if not isinstance(value, list):
        return False

    if len(value) == 0:
        return True

    first = value[0]

    if not isinstance(first, dict):
        return False

    possible_station_keys = {
        "id",
        "stationId",
        "stationName",
        "gegrLat",
        "gegrLon",
        "city",
        "addressStreet",
        "Nazwa stacji",
        "Identyfikator stacji",
    }

    return any(key in first for key in possible_station_keys)


def _extract_station_records(
    data: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Wyciąga listę stacji z odpowiedzi API.

    Funkcja jest elastyczna, ponieważ API może zwrócić:
    - bezpośrednio listę,
    - słownik z kluczem content,
    - słownik z kluczem data/items/results,
    - JSON-LD z kluczem @graph.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        raise TypeError("Dane GIOŚ muszą być listą albo słownikiem.")

    candidate_keys = [
        "content",
        "data",
        "items",
        "results",
        "stations",
        "Lista stacji pomiarowych",
        "@graph",
    ]

    for key in candidate_keys:
        value = data.get(key)

        if _looks_like_station_list(value):
            return value

    for key, value in data.items():
        if _looks_like_station_list(value):
            logger.info("Lista stacji GIOŚ znaleziona w kluczu: %s", key)
            return value

    logger.error("Nie znaleziono listy stacji w odpowiedzi GIOŚ. Klucze: %s", list(data.keys()))
    raise KeyError("Nie znaleziono listy stacji w odpowiedzi GIOŚ.")


def _get_total_pages(data: dict[str, Any] | list[dict[str, Any]]) -> Optional[int]:
    """
    Próbuje odczytać liczbę stron z odpowiedzi API.
    Jeżeli API jej nie zwraca, funkcja zwraca None.
    """

    if not isinstance(data, dict):
        return None

    direct_keys = [
        "totalPages",
        "pages_total",
        "total_pages",
        "pageCount",
    ]

    for key in direct_keys:
        value = data.get(key)

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                logger.info("Nie udało się odczytać liczby stron GIOŚ z klucza %s.", key)

    page_info = data.get("page")

    if isinstance(page_info, dict):
        for key in ["totalPages", "total_pages", "pageCount"]:
            value = page_info.get(key)

            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    logger.info("Nie udało się odczytać liczby stron GIOŚ z page.%s.", key)

    return None


def fetch_gios_stations() -> dict[str, Any]:
    """
    Pobiera listę stacji GIOŚ.

    Obsługuje paginację, ale działa też wtedy, gdy API zwróci od razu całą listę.
    """

    logger.info("Rozpoczynam pobieranie listy stacji GIOŚ.")

    session = _create_session()

    first_page_data = _request_gios_stations_page(
        session=session,
        page=0,
        size=GIOS_PAGE_SIZE,
    )

    first_records = _extract_station_records(first_page_data)
    all_records = list(first_records)

    total_pages = _get_total_pages(first_page_data)

    if total_pages is None:
        logger.info(
            "GIOŚ nie zwrócił liczby stron. Przyjmuję strategię: "
            "pobieram do momentu pustej strony lub limitu."
        )

        if isinstance(first_page_data, list):
            logger.info("GIOŚ zwrócił listę bez metadanych paginacji. Kończę na pierwszym pobraniu.")
            total_pages = 1
        elif len(first_records) < GIOS_PAGE_SIZE:
            logger.info("Pierwsza strona ma mniej rekordów niż size. Kończę na pierwszym pobraniu.")
            total_pages = 1
        else:
            total_pages = GIOS_MAX_PAGES

    total_pages = max(1, min(total_pages, GIOS_MAX_PAGES))

    logger.info("GIOŚ total_pages do pobrania: %s", total_pages)

    for page in range(1, total_pages):
        time.sleep(GIOS_PAGE_DELAY_SECONDS)

        page_data = _request_gios_stations_page(
            session=session,
            page=page,
            size=GIOS_PAGE_SIZE,
        )

        page_records = _extract_station_records(page_data)

        if len(page_records) == 0:
            logger.info("Strona GIOŚ page=%s jest pusta. Kończę pobieranie.", page)
            break

        all_records.extend(page_records)

        if len(page_records) < GIOS_PAGE_SIZE:
            logger.info("Strona GIOŚ page=%s ma mniej rekordów niż size. Kończę pobieranie.", page)
            break

    if len(all_records) == 0:
        logger.error("Nie pobrano żadnych stacji GIOŚ.")
        raise ValueError("Brak rekordów stacji GIOŚ.")

    result = {
        "stations": all_records,
        "downloaded_records": len(all_records),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }

    logger.info("Pobrano stacje GIOŚ. Liczba rekordów: %s", len(all_records))

    return result


def save_raw_gios_stations_json(data: dict[str, Any]) -> Path:
    """
    Zapisuje surową odpowiedź GIOŚ do pliku JSON.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RAW_GIOS_DIR / f"gios_stations_raw_{timestamp}.json"

    try:
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    except OSError as error:
        logger.error("Nie udało się zapisać surowego JSON GIOŚ: %s", error)
        raise RuntimeError(f"Nie udało się zapisać pliku JSON GIOŚ: {output_path}") from error

    logger.info("Zapisano surowy JSON GIOŚ: %s", output_path)

    return output_path


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """
    Zwraca pierwszą istniejącą kolumnę z listy kandydatów.
    """

    for column in candidates:
        if column in df.columns:
            return column

    return None


def _series_or_na(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """
    Zwraca kolumnę, jeśli istnieje, albo pustą serię.
    """

    column = _first_existing_column(df, candidates)

    if column is None:
        return pd.Series([pd.NA] * len(df), index=df.index)

    return df[column]


def normalize_gios_stations(data: dict[str, Any]) -> pd.DataFrame:
    """
    Normalizuje listę stacji GIOŚ do jednej płaskiej tabeli.
    """

    logger.info("Rozpoczynam normalizację stacji GIOŚ.")

    if "stations" not in data:
        logger.error("Brak klucza 'stations' w danych GIOŚ. Klucze: %s", list(data.keys()))
        raise KeyError("Brak klucza 'stations' w danych GIOŚ.")

    records = data["stations"]

    if not isinstance(records, list):
        logger.error("Pole 'stations' nie jest listą. Typ: %s", type(records))
        raise TypeError("Pole 'stations' nie jest listą.")

    if len(records) == 0:
        logger.error("Lista stacji GIOŚ jest pusta.")
        raise ValueError("Lista stacji GIOŚ jest pusta.")

    df = pd.json_normalize(records)

    if df.empty:
        logger.error("Po normalizacji tabela stacji GIOŚ jest pusta.")
        raise ValueError("Po normalizacji tabela stacji GIOŚ jest pusta.")

    logger.info("Kolumny GIOŚ po normalizacji: %s", list(df.columns))

    output = pd.DataFrame(index=df.index)

    output["gios_station_id"] = _series_or_na(
        df,
        [
            "id",
            "stationId",
            "station_id",
            "Identyfikator stacji",
        ],
    )

    output["station_name"] = _series_or_na(
        df,
        [
            "stationName",
            "station_name",
            "Nazwa stacji",
            "name",
        ],
    )

    output["latitude"] = _series_or_na(
        df,
        [
            "gegrLat",
            "latitude",
            "lat",
            "WGS84 φ N",
        ],
    )

    output["longitude"] = _series_or_na(
        df,
        [
            "gegrLon",
            "longitude",
            "lon",
            "lng",
            "WGS84 λ E",
        ],
    )

    output["city"] = _series_or_na(
        df,
        [
            "city.name",
            "city",
            "Miejscowość",
        ],
    )

    output["commune"] = _series_or_na(
        df,
        [
            "city.commune.communeName",
            "communeName",
            "Gmina",
        ],
    )

    output["district"] = _series_or_na(
        df,
        [
            "city.commune.districtName",
            "districtName",
            "Powiat",
        ],
    )

    output["province"] = _series_or_na(
        df,
        [
            "city.commune.provinceName",
            "provinceName",
            "Województwo",
        ],
    )

    output["address_street"] = _series_or_na(
        df,
        [
            "addressStreet",
            "street",
            "Ulica",
        ],
    )

    output["source"] = "GIOS"
    output["downloaded_at"] = datetime.now()

    output["latitude"] = (
        output["latitude"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )

    output["longitude"] = (
        output["longitude"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )

    output["latitude"] = pd.to_numeric(output["latitude"], errors="coerce")
    output["longitude"] = pd.to_numeric(output["longitude"], errors="coerce")

    before_coordinates = len(output)
    output = output.dropna(subset=["latitude", "longitude"]).copy()
    removed_coordinates = before_coordinates - len(output)

    if removed_coordinates > 0:
        logger.warning("Usunięto stacje GIOŚ bez współrzędnych: %s", removed_coordinates)

    before_range = len(output)

    output = output[
        output["latitude"].between(-90, 90, inclusive="both")
        & output["longitude"].between(-180, 180, inclusive="both")
    ].copy()

    removed_range = before_range - len(output)

    if removed_range > 0:
        logger.warning("Usunięto stacje GIOŚ z błędnym zakresem współrzędnych: %s", removed_range)

    output["gios_station_id"] = output["gios_station_id"].astype(str).str.strip()

    missing_id_mask = (
        output["gios_station_id"].isin(["", "nan", "None", "<NA>", "NaN"])
        | output["gios_station_id"].isna()
    )

    if missing_id_mask.sum() > 0:
        logger.warning(
            "Liczba stacji GIOŚ bez ID. Zostanie utworzone ID awaryjne: %s",
            missing_id_mask.sum(),
        )

    output.loc[missing_id_mask, "gios_station_id"] = output.loc[missing_id_mask].apply(
        lambda row: _make_hash_id(
            "UNKNOWN_GIOS",
            row["station_name"],
            row["latitude"],
            row["longitude"],
        ),
        axis=1,
    )

    output["station_id"] = "GIOS_" + output["gios_station_id"].astype(str)

    final_columns = [
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

    output = output[final_columns]

    before_duplicates = len(output)
    output = output.drop_duplicates(subset=["station_id"]).reset_index(drop=True)
    removed_duplicates = before_duplicates - len(output)

    if removed_duplicates > 0:
        logger.warning("Usunięto duplikaty stacji GIOŚ: %s", removed_duplicates)

    if output.empty:
        logger.error("Po czyszczeniu tabela stacji GIOŚ jest pusta.")
        raise ValueError("Po czyszczeniu tabela stacji GIOŚ jest pusta.")

    logger.info("Normalizacja stacji GIOŚ zakończona. Liczba stacji: %s", len(output))

    return output


def save_gios_stations_csv(df: pd.DataFrame) -> Path:
    """
    Zapisuje stacje GIOŚ do CSV.
    """

    if df is None or df.empty:
        logger.error("Próba zapisu pustej tabeli stacji GIOŚ.")
        raise ValueError("Nie można zapisać pustej tabeli stacji GIOŚ.")

    try:
        df.to_csv(GIOS_STATIONS_CSV, index=False, encoding="utf-8-sig")

    except OSError as error:
        logger.error("Nie udało się zapisać CSV stacji GIOŚ: %s", error)
        raise RuntimeError(f"Nie udało się zapisać CSV stacji GIOŚ: {GIOS_STATIONS_CSV}") from error

    logger.info("Zapisano CSV stacji GIOŚ: %s", GIOS_STATIONS_CSV)

    return GIOS_STATIONS_CSV


def run_gios_stations_extraction() -> pd.DataFrame:
    """
    Pełny proces dla stacji GIOŚ:
    pobierz dane -> zapisz raw JSON -> znormalizuj -> zapisz CSV.
    """

    data = fetch_gios_stations()

    save_raw_gios_stations_json(data)

    df = normalize_gios_stations(data)

    save_gios_stations_csv(df)

    logger.info("Proces pobierania stacji GIOŚ zakończony poprawnie.")

    print(f"Liczba stacji GIOŚ: {len(df)}")
    print("Kolumny stacji GIOŚ:")
    print(list(df.columns))

    return df