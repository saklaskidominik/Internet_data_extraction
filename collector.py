import argparse
import time
from datetime import datetime

from run_full_pipeline import run_full_pipeline
from src.utils import setup_logger


logger = setup_logger(__name__)


def run_collector(interval_minutes: int) -> None:
    """
    Uruchamia pełny pipeline cyklicznie co określoną liczbę minut.

    Program działa lokalnie:
    - komputer musi być włączony,
    - terminal musi pozostać otwarty,
    - środowisko .venv musi być aktywne.
    """

    if interval_minutes <= 0:
        raise ValueError("Interwał musi być większy od 0 minut.")

    interval_seconds = interval_minutes * 60

    print("=" * 80)
    print("START AUTOMATYCZNEGO KOLEKTORA DANYCH")
    print("=" * 80)
    print(f"Pełny pipeline będzie uruchamiany co {interval_minutes} minut.")
    print("Aby zatrzymać program, naciśnij CTRL + C.")
    print("=" * 80)

    logger.info(
        "Start automatycznego kolektora pełnego pipeline. Interwał: %s minut.",
        interval_minutes,
    )

    cycle_number = 1

    while True:
        print()
        print("=" * 80)
        print(f"CYKL {cycle_number} — start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        logger.info("Start cyklu kolektora: %s", cycle_number)

        try:
            run_full_pipeline()

            print("=" * 80)
            print(f"CYKL {cycle_number} ZAKOŃCZONY POPRAWNIE")
            print("=" * 80)

            logger.info("Cykl kolektora zakończony poprawnie: %s", cycle_number)

        except Exception as error:
            print("=" * 80)
            print(f"BŁĄD W CYKLU {cycle_number}")
            print("=" * 80)
            print(f"Szczegóły błędu: {error}")
            print("Program nie zostanie zatrzymany — kolejna próba będzie w następnym cyklu.")
            print("Więcej informacji znajdziesz w logs/project.log.")

            logger.exception(
                "Błąd w cyklu kolektora %s: %s",
                cycle_number,
                error,
            )

        cycle_number += 1

        print()
        print(f"Następny cykl za {interval_minutes} minut.")
        print("Aby zatrzymać, naciśnij CTRL + C.")

        try:
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print()
            print("=" * 80)
            print("AUTOMATYCZNY KOLEKTOR ZATRZYMANY PRZEZ UŻYTKOWNIKA")
            print("=" * 80)

            logger.info("Automatyczny kolektor zatrzymany przez użytkownika.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automatyczny lokalny kolektor danych środowiskowych."
    )

    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Co ile minut uruchamiać pełny pipeline. Domyślnie: 60.",
    )

    args = parser.parse_args()

    run_collector(interval_minutes=args.interval_minutes)


if __name__ == "__main__":
    main()