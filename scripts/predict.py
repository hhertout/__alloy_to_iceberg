from dotenv import load_dotenv

from utils.askii_art import print_ascii_art
from utils.logging import get_logger
from utils.telemetry import setup_telemetry, shutdown_telemetry


def main() -> None:
    print_ascii_art()
    load_dotenv()
    log = get_logger("predict")

    try:
        pass
    except KeyboardInterrupt:
        log.info("Prediction script interrupted by user.")
    except Exception as e:
        log.error("An error occurred: %s", e)
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    setup_telemetry()
    main()
