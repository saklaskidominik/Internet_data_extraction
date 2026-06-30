from src.pipeline import run_esa_pipeline
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Jednorazowe uruchomienie pipeline'u ESA.

    Ten plik uruchamiamy wtedy, kiedy chcemy ręcznie pobrać dane jeden raz.
    """

    print("Start projektu: ekstrakcja i integracja danych środowiskowych")
    print("-" * 70)

    try:
        summary = run_esa_pipeline()

        database_summary = summary["database_summary"]

        print("Pipeline ESA wykonany poprawnie.")
        print("-" * 70)
        print("Podsumowanie aktualnego uruchomienia:")
        print(f"Liczba szkół / punktów pomiarowych: {summary['current_run_stations']}")
        print(f"Liczba pomiarów w aktualnym pobraniu: {summary['current_run_measurements']}")
        print(f"Nowe stacje zapisane do bazy: {summary['inserted_stations']}")
        print(f"Nowe pomiary zapisane do bazy: {summary['inserted_measurements']}")

        print("-" * 70)
        print("Podsumowanie całej bazy danych:")
        print(f"Liczba stacji w bazie: {database_summary['stations_count']}")
        print(f"Liczba pomiarów w bazie: {database_summary['measurements_count']}")
        print(f"Najstarszy czas pomiaru: {database_summary['min_measured_at']}")
        print(f"Najnowszy czas pomiaru: {database_summary['max_measured_at']}")

        print("-" * 70)
        print("ETAP ESA + baza danych zakończony poprawnie.")

    except Exception as error:
        logger.exception("Program zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()
    