from src.database import (
    get_environmental_snapshot_summary,
    save_environmental_snapshot_to_database,
)
from src.final_dataset import run_environmental_snapshot_build
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test budowy finalnego zbioru analitycznego.
    """

    print("Start testu finalnego zbioru environmental_snapshot")
    print("-" * 70)

    try:
        snapshot_df = run_environmental_snapshot_build()

        print("-" * 70)
        print("Podgląd finalnego zbioru:")
        print(snapshot_df.head())

        print("-" * 70)
        print("Podstawowe statystyki PM10 i PM2.5:")
        print(snapshot_df[["pm10", "pm25"]].describe())

        print("-" * 70)
        print("Zapisuję finalny zbiór do bazy DuckDB...")

        inserted_count = save_environmental_snapshot_to_database(snapshot_df)

        print(f"Liczba rekordów environmental_snapshot zapisanych do bazy: {inserted_count}")

        summary = get_environmental_snapshot_summary()

        print("-" * 70)
        print("Podsumowanie environmental_snapshot w bazie:")
        print(f"Liczba rekordów: {summary['total_count']}")
        print(f"Liczba miast ESA: {summary['city_count']}")
        print(f"Średnie PM10: {summary['avg_pm10']}")
        print(f"Średnie PM2.5: {summary['avg_pm25']}")
        print(f"Średnia odległość do GIOŚ [km]: {summary['avg_distance_to_gios_km']}")
        print(f"Średnia odległość do IMGW [km]: {summary['avg_distance_to_imgw_km']}")

        print("-" * 70)
        print("Top 10 najwyższych wartości PM10:")
        print(
            snapshot_df[
                [
                    "school_name",
                    "esa_city",
                    "pm10",
                    "pm25",
                    "nearest_gios_station_name",
                    "nearest_imgw_station_name",
                    "imgw_temperature",
                    "imgw_relative_humidity",
                ]
            ]
            .sort_values("pm10", ascending=False)
            .head(10)
        )

        print("-" * 70)
        print("Test finalnego zbioru zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test finalnego zbioru zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE FINALNEGO ZBIORU.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()