from dotenv import load_dotenv

from utils.askii_art import print_ascii_art
from utils.logging import get_logger


def main() -> None:
    print_ascii_art()
    load_dotenv()
    _log = get_logger("predict")


if __name__ == "__main__":
    main()
