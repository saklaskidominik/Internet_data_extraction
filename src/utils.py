import logging
from logging.handlers import RotatingFileHandler

from src.config import LOGS_DIR


def setup_logger(name: str = "environmental_data_project") -> logging.Logger:
    """
    Konfiguruje logger projektu.

    Logger zapisuje komunikaty:
    - do terminala,
    - do pliku logs/project.log.

    RotatingFileHandler sprawia, że plik logów nie rośnie bez końca.
    """

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_file = LOGS_DIR / "project.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger