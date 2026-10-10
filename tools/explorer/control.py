#!/usr/bin/env python3
"""Calculate the observed A1/mod-97 control for a message base.

The base is the complete message before the final ``;control`` field.
The formula is confirmed only for the tested ASCII mapping and non-ASCII
filtering examples; this does not specify the original parser's full behavior.
"""
from __future__ import annotations

import argparse


def control(base: str) -> int:
    """Return the observed control for ``base`` (which omits ``;control``).

    ASCII letters map to A=1 through Z=26, ASCII digits keep their value, and
    other ASCII characters are ignored. Non-ASCII code points are filtered
    before any case conversion or normalization. The resulting decimal digit
    stream has ``00`` appended. The checksum is streamed modulo 97, and the
    returned control is ``98 - remainder`` without a final modulo operation
    (range 2..98). No large integer is constructed. Non-ASCII code points are
    filtered without normalization, as observed in the tested cases.
    """
    if not isinstance(base, str):
        raise TypeError("base debe ser str")

    remainder = 0
    for char in base:
        codepoint = ord(char)
        if codepoint > 0x7F:
            continue

        if "0" <= char <= "9":
            digits = char
        elif "A" <= char <= "Z":
            digits = str(codepoint - ord("A") + 1)
        elif "a" <= char <= "z":
            digits = str(codepoint - ord("a") + 1)
        else:
            continue

        for digit in digits:
            remainder = (remainder * 10 + ord(digit) - ord("0")) % 97

    remainder = remainder * 100 % 97
    return 98 - remainder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "base",
        nargs="?",
        help="mensaje sin el campo final ;control (fórmula A1/mod-97)",
    )
    args = parser.parse_args(argv)
    if args.base is None:
        parser.print_help()
        return 0
    if not args.base:
        parser.error("base debe ser no vacía y omitir el campo final ;control")

    print(control(args.base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
