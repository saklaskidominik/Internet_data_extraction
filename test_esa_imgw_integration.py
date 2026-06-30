from src.database import (
    get_esa_imgw_weather_summary,
    save_esa_imgw_weather_to_database,
)
from src.weather_integration import run_esa_imgw_weather_integration
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test integracji ESA z najbliższą stacją IMGW i aktualną pogodą.
    """

    print("Start testu integracji ESA + IMGW")
    print("-" * 70)

    try:
        integrated_df = run_esa_imgw_weather_integration()

        print("-" * 70)
        print("Podgląd integracji ESA-IMGW:")
        print(integrated_df.head())

        print("-" * 70)
        print("Statystyki odległości ESA → najbliższa stacja IMGW:")
        print(integrated_df["distance_to_imgw_km"].describe())

        print("-" * 70)
        print("Zapisuję integrację ESA-IMGW do bazy DuckDB...")

        inserted_count = save_esa_imgw_weather_to_database(integrated_df)

        print(f"Liczba rekordów ESA-IMGW zapisanych do bazy: {inserted_count}")

        summary = get_esa_imgw_weather_summary()

        print("-" * 70)
        print("Podsumowanie ESA-IMGW w bazie:")
        print(f"Liczba rekordów: {summary['total_count']}")
        print(f"Liczba wykorzystanych stacji IMGW: {summary['nearest_imgw_station_count']}")
        print(f"Minimalna odległość [km]: {summary['min_distance_km']}")
        print(f"Średnia odległość [km]: {summary['avg_distance_km']}")
        print(f"Maksymalna odległość [km]: {summary['max_distance_km']}")

        print("-" * 70)
        print("Najdalsze dopasowania ESA-IMGW:")
        print(
            integrated_df[
                [
                    "school_name",
                    "esa_city",
                    "nearest_imgw_station_name",
                    "distance_to_imgw_km",
                    "imgw_temperature",
                    "imgw_relative_humidity",
                    "imgw_pressure",
                ]
            ]
            .sort_values("distance_to_imgw_km", ascending=False)
            .head(10)
        )

        print("-" * 70)
        print("Test integracji ESA-IMGW zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test integracji ESA-IMGW zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE INTEGRACJI ESA-IMGW.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()