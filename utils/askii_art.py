RESET = "\033[0m"

# Flame gradient: yellow → orange → dark orange → red
_FLAME_COLORS = [
    "\033[38;5;220m",  # yellow
    "\033[38;5;214m",  # light orange
    "\033[38;5;208m",  # orange
    "\033[38;5;202m",  # dark orange
    "\033[38;5;196m",  # red
    "\033[38;5;160m",  # dark red
]

_FLAME_LINES = [
    r"                        .****.",
    r"                     .*########*.",
    r"                   .################.",
    r"                  .######    .######*.",
    r"                 .#####   *##  .#####.",
    r"                 .####   *####  .####.",
    r"                  .###.   *##  .####.",
    r"                   .####.    .#####.",
    r"                     .*##########*.",
    r"                   .##*.  .####*.",
    r"                  .#####.   *##.",
    r"                  .######.    *.",
    r"                   .*####*.",
    r"                      *##*.",
    r"                        *.",
]

def print_ascii_art() -> None:
    n = len(_FLAME_LINES)
    print("\n")
    for i, line in enumerate(_FLAME_LINES):
        color_idx = int(i / n * len(_FLAME_COLORS))
        color_idx = min(color_idx, len(_FLAME_COLORS) - 1)
        print(f"{_FLAME_COLORS[color_idx]}{line}{RESET}")
    print("\n")