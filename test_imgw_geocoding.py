from src.database import (
    get_imgw_station_metadata_summary,
    save_imgw_station_metadata_to_database,
)
from src.geocode_imgw_stations import run_imgw_station_geocoding
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test geokodowania stacji IMGW i zapisu do bazy DuckDB.
    """

    print("Start testu geokodowania stacji IMGW")
    print("-" * 70)

    try:
        imgw_stations = run_imgw_station_geocoding()

        print("-" * 70)
        print("Podgląd zgeokodowanych stacji IMGW:")
        print(imgw_stations.head())

        print("-" * 70)
        print("Zapisuję zgeokodowane stacje IMGW do bazy DuckDB...")

        inserted_count = save_imgw_station_metadata_to_database(imgw_stations)

        print(f"Liczba zgeokodowanych stacji IMGW zapisanych do bazy: {inserted_count}")

        summary = get_imgw_station_metadata_summary()

        print("-" * 70)
        print("Podsumowanie stacji IMGW w bazie:")
        print(f"Liczba stacji IMGW w bazie: {summary['total_count']}")
        print(f"Liczba aktywnych stacji: {summary['active_count']}")
        print(f"Zakres szerokości geograficznej: {summary['min_latitude']} - {summary['max_latitude']}")
        print(f"Zakres długości geograficznej: {summary['min_longitude']} - {summary['max_longitude']}")

        print("-" * 70)
        print("Test geokodowania stacji IMGW zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test geokodowania stacji IMGW zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE GEOKODOWANIA IMGW.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()