from src.database import (
    get_esa_gios_nearest_summary,
    save_esa_gios_nearest_to_database,
)
from src.spatial_integration import run_esa_gios_spatial_integration
from src.utils import setup_logger


logger = setup_logger(__name__)


def main() -> None:
    """
    Test integracji przestrzennej ESA + GIOŚ.
    """

    print("Start testu integracji przestrzennej ESA + GIOŚ")
    print("-" * 70)

    try:
        nearest_df = run_esa_gios_spatial_integration()

        print("-" * 70)
        print("Podgląd najbliższych dopasowań ESA-GIOŚ:")
        print(nearest_df.head())

        print("-" * 70)
        print("Statystyki odległości ESA → najbliższa stacja GIOŚ:")
        print(nearest_df["distance_km"].describe())

        print("-" * 70)
        print("Zapisuję tabelę ESA-GIOŚ do bazy DuckDB...")

        inserted_count = save_esa_gios_nearest_to_database(nearest_df)

        print(f"Liczba rekordów ESA-GIOŚ zapisanych do bazy: {inserted_count}")

        summary = get_esa_gios_nearest_summary()

        print("-" * 70)
        print("Podsumowanie ESA-GIOŚ w bazie:")
        print(f"Liczba rekordów: {summary['total_count']}")
        print(f"Minimalna odległość [km]: {summary['min_distance_km']}")
        print(f"Średnia odległość [km]: {summary['avg_distance_km']}")
        print(f"Maksymalna odległość [km]: {summary['max_distance_km']}")

        print("-" * 70)
        print("Najdalsze dopasowania:")
        print(
            nearest_df[
                [
                    "school_name",
                    "esa_city",
                    "nearest_gios_station_name",
                    "gios_city",
                    "gios_province",
                    "distance_km",
                ]
            ]
            .sort_values("distance_km", ascending=False)
            .head(10)
        )

        print("-" * 70)
        print("Test integracji przestrzennej zakończony poprawnie.")

    except Exception as error:
        logger.exception("Test integracji przestrzennej zakończył się błędem: %s", error)

        print("-" * 70)
        print("WYSTĄPIŁ BŁĄD W TEŚCIE INTEGRACJI PRZESTRZENNEJ.")
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()