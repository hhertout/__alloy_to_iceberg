from dotenv import load_dotenv

from utils.logging import get_logger
from utils.askii_art import print_ascii_art

def main():
    print_ascii_art()
    load_dotenv()
    _log = get_logger("predict")

if __name__ == "__main__":
    main()
