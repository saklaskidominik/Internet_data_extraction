from src.database import (
    get_database_summary,
    get_environmental_snapshot_summary,
    get_esa_gios_nearest_summary,
    get_esa_imgw_weather_summary,
    get_gios_database_summary,
    get_imgw_station_metadata_summary,
    get_weather_database_summary,
    save_esa_gios_nearest_to_database,
    save_esa_imgw_weather_to_database,
    save_environmental_snapshot_to_database,
    save_gios_stations_to_database,
    save_imgw_station_metadata_to_database,
    save_weather_to_database,
)
from src.extract_gios import run_gios_stations_extraction
from src.extract_weather import run_imgw_weather_extraction
from src.final_dataset import run_environmental_snapshot_build
from src.geocode_imgw_stations import run_imgw_station_geocoding
from src.pipeline import run_esa_pipeline
from src.spatial_integration import run_esa_gios_spatial_integration
from src.utils import setup_logger
from src.weather_integration import run_esa_imgw_weather_integration


logger = setup_logger(__name__)


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def run_full_pipeline() -> None:
    """
    Uruchamia pełny pipeline projektu:
    1. ESA
    2. GIOŚ
    3. IMGW pogoda
    4. Geokodowanie stacji IMGW
    5. Integracja ESA-GIOŚ
    6. Integracja ESA-IMGW
    7. Finalny zbiór environmental_snapshot
    """

    print_section("START PEŁNEGO PIPELINE PROJEKTU")

    # ========================================================
    # 1. ESA
    # ========================================================

    print_section("ETAP 1 — ESA: pobieranie, czyszczenie i zapis do bazy")

    esa_summary = run_esa_pipeline()

    print(f"ESA — liczba punktów w aktualnym pobraniu: {esa_summary['current_run_stations']}")
    print(f"ESA — liczba pomiarów w aktualnym pobraniu: {esa_summary['current_run_measurements']}")
    print(f"ESA — nowe stacje zapisane do bazy: {esa_summary['inserted_stations']}")
    print(f"ESA — nowe pomiary zapisane do bazy: {esa_summary['inserted_measurements']}")

    esa_db_summary = get_database_summary()

    print(f"ESA — liczba stacji w bazie: {esa_db_summary['stations_count']}")
    print(f"ESA — liczba pomiarów w bazie: {esa_db_summary['measurements_count']}")
    print(f"ESA — najnowszy pomiar: {esa_db_summary['max_measured_at']}")

    # ========================================================
    # 2. GIOŚ
    # ========================================================

    print_section("ETAP 2 — GIOŚ: pobieranie stacji i zapis do bazy")

    gios_stations = run_gios_stations_extraction()
    inserted_gios = save_gios_stations_to_database(gios_stations)

    gios_summary = get_gios_database_summary()

    print(f"GIOŚ — nowe stacje zapisane do bazy: {inserted_gios}")
    print(f"GIOŚ — liczba stacji w bazie: {gios_summary['gios_stations_count']}")
    print(f"GIOŚ — liczba województw: {gios_summary['province_count']}")

    # ========================================================
    # 3. IMGW weather
    # ========================================================

    print_section("ETAP 3 — IMGW: pobieranie aktualnych danych pogodowych")

    weather_df = run_imgw_weather_extraction()
    inserted_weather = save_weather_to_database(weather_df)

    weather_summary = get_weather_database_summary()

    print(f"IMGW — nowe pomiary pogodowe zapisane do bazy: {inserted_weather}")
    print(f"IMGW — liczba pomiarów w bazie: {weather_summary['total_count']}")
    print(f"IMGW — liczba stacji pogodowych: {weather_summary['station_count']}")
    print(f"IMGW — najnowszy pomiar: {weather_summary['max_measured_at']}")

    # ========================================================
    # 4. IMGW geocoding
    # ========================================================

    print_section("ETAP 4 — IMGW: lokalizacje stacji pogodowych")

    imgw_stations = run_imgw_station_geocoding()
    inserted_imgw_stations = save_imgw_station_metadata_to_database(imgw_stations)

    imgw_station_summary = get_imgw_station_metadata_summary()

    print(f"IMGW — zgeokodowane stacje zapisane do bazy: {inserted_imgw_stations}")
    print(f"IMGW — liczba stacji w bazie: {imgw_station_summary['total_count']}")
    print(f"IMGW — liczba aktywnych stacji: {imgw_station_summary['active_count']}")

    # ========================================================
    # 5. ESA-GIOŚ
    # ========================================================

    print_section("ETAP 5 — integracja ESA + GIOŚ")

    esa_gios_df = run_esa_gios_spatial_integration()
    inserted_esa_gios = save_esa_gios_nearest_to_database(esa_gios_df)

    esa_gios_summary = get_esa_gios_nearest_summary()

    print(f"ESA-GIOŚ — liczba rekordów zapisanych do bazy: {inserted_esa_gios}")
    print(f"ESA-GIOŚ — średnia odległość [km]: {esa_gios_summary['avg_distance_km']}")
    print(f"ESA-GIOŚ — maksymalna odległość [km]: {esa_gios_summary['max_distance_km']}")

    # ========================================================
    # 6. ESA-IMGW
    # ========================================================

    print_section("ETAP 6 — integracja ESA + IMGW")

    esa_imgw_df = run_esa_imgw_weather_integration()
    inserted_esa_imgw = save_esa_imgw_weather_to_database(esa_imgw_df)

    esa_imgw_summary = get_esa_imgw_weather_summary()

    print(f"ESA-IMGW — liczba rekordów zapisanych do bazy: {inserted_esa_imgw}")
    print(f"ESA-IMGW — liczba wykorzystanych stacji IMGW: {esa_imgw_summary['nearest_imgw_station_count']}")
    print(f"ESA-IMGW — średnia odległość [km]: {esa_imgw_summary['avg_distance_km']}")
    print(f"ESA-IMGW — maksymalna odległość [km]: {esa_imgw_summary['max_distance_km']}")

    # ========================================================
    # 7. Finalny dataset
    # ========================================================

    print_section("ETAP 7 — finalny zbiór environmental_snapshot")

    snapshot_df = run_environmental_snapshot_build()
    inserted_snapshot = save_environmental_snapshot_to_database(snapshot_df)

    final_summary = get_environmental_snapshot_summary()

    print(f"FINAL — liczba rekordów zapisanych do bazy: {inserted_snapshot}")
    print(f"FINAL — liczba miast ESA: {final_summary['city_count']}")
    print(f"FINAL — średnie PM10: {final_summary['avg_pm10']}")
    print(f"FINAL — średnie PM2.5: {final_summary['avg_pm25']}")
    print(f"FINAL — średnia odległość do GIOŚ [km]: {final_summary['avg_distance_to_gios_km']}")
    print(f"FINAL — średnia odległość do IMGW [km]: {final_summary['avg_distance_to_imgw_km']}")

    print_section("PEŁNY PIPELINE ZAKOŃCZONY POPRAWNIE")


def main() -> None:
    try:
        run_full_pipeline()

    except Exception as error:
        logger.exception("Pełny pipeline zakończył się błędem: %s", error)

        print()
        print("=" * 80)
        print("WYSTĄPIŁ BŁĄD W PEŁNYM PIPELINE")
        print("=" * 80)
        print(f"Szczegóły błędu: {error}")
        print("Więcej informacji znajdziesz w pliku logs/project.log.")


if __name__ == "__main__":
    main()