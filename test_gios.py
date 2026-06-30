from src.database import get_gios_database_summary, save_gios_stations_to_database
from src.extract_gios import run_gios_stations_extraction
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test pobierania stacji GIOŚ oraz zapisu do bazy DuckDB.
    """

    print("Start testu GIOŚ: pobieranie listy stacji pomiarowych")
    print("-" * 70)

    try:
        gios_stations = run_gios_stations_extraction()

        print("-" * 70)
        print("Podgląd stacji GIOŚ:")
        print(gios_stations.head())

        print("-" * 70)
        print("Zapisuję stacje GIOŚ do bazy DuckDB...")

        inserted_gios_stations = save_gios_stations_to_database(gios_stations)

        print(f"Nowe stacje GIOŚ zapisane do bazy: {inserted_gios_stations}")

        gios_summary = get_gios_database_summary()

        print("-" * 70)
        print("Podsumowanie GIOŚ w bazie:")
        print(f"Liczba stacji GIOŚ w bazie: {gios_summary['gios_stations_count']}")
        print(f"Liczba województw w danych GIOŚ: {gios_summary['province_count']}")

        print("-" * 70)
        print("Test GIOŚ zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test GIOŚ zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE GIOŚ.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()