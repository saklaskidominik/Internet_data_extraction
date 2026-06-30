from src.database import get_weather_database_summary, save_weather_to_database
from src.extract_weather import run_imgw_weather_extraction
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test pobierania danych pogodowych IMGW i zapisu do bazy DuckDB.
    """

    print("Start testu IMGW: pobieranie danych pogodowych")
    print("-" * 70)

    try:
        weather_df = run_imgw_weather_extraction()

        print("-" * 70)
        print("Podgląd danych pogodowych IMGW:")
        print(weather_df.head())

        print("-" * 70)
        print("Zapisuję dane pogodowe IMGW do bazy DuckDB...")

        inserted_weather = save_weather_to_database(weather_df)

        print(f"Nowe pomiary pogodowe IMGW zapisane do bazy: {inserted_weather}")

        summary = get_weather_database_summary()

        print("-" * 70)
        print("Podsumowanie IMGW w bazie:")
        print(f"Liczba pomiarów pogodowych w bazie: {summary['total_count']}")
        print(f"Liczba stacji pogodowych w bazie: {summary['station_count']}")
        print(f"Najstarszy czas pomiaru: {summary['min_measured_at']}")
        print(f"Najnowszy czas pomiaru: {summary['max_measured_at']}")

        print("-" * 70)
        print("Test IMGW zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test IMGW zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE IMGW.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()