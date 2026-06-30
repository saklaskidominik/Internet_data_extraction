from typing import Dict, Any

from src.database import get_database_summary, save_esa_to_database
from src.extract_esa import run_esa_extraction
from src.transform import clean_esa_data, save_esa_clean_tables
from src.utils import setup_logger


logger = setup_logger(__name__)


def run_esa_pipeline() -> Dict[str, Any]:
    """
    Uruchamia pełny pipeline ESA:

    1. pobranie danych z API ESA,
    2. zapis surowego JSON,
    3. normalizacja JSON do tabeli,
    4. czyszczenie danych,
    5. zapis czystych CSV,
    6. zapis do bazy DuckDB,
    7. zwrot krótkiego podsumowania.

    Funkcja jest wydzielona osobno, żeby można było jej używać:
    - jednorazowo w main.py,
    - cyklicznie w collector.py.
    """

    logger.info("Start pipeline ESA.")

    esa_raw_df = run_esa_extraction()

    logger.info("Czyszczę i normalizuję dane ESA.")

    esa_stations, esa_measurements = clean_esa_data(esa_raw_df)

    if esa_stations.empty:
        raise ValueError("Tabela szkół ESA jest pusta po czyszczeniu.")

    if esa_measurements.empty:
        raise ValueError("Tabela pomiarów ESA jest pusta po czyszczeniu.")

    stations_path, measurements_path = save_esa_clean_tables(
        esa_stations,
        esa_measurements,
    )

    inserted_stations, inserted_measurements = save_esa_to_database(
        esa_stations,
        esa_measurements,
    )

    database_summary = get_database_summary()

    summary = {
        "current_run_stations": len(esa_stations),
        "current_run_measurements": len(esa_measurements),
        "inserted_stations": inserted_stations,
        "inserted_measurements": inserted_measurements,
        "stations_csv": stations_path,
        "measurements_csv": measurements_path,
        "database_summary": database_summary,
    }

    logger.info("Pipeline ESA zakończony poprawnie. Podsumowanie: %s", summary)

    return summary