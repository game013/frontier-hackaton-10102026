"""Offline checks against observed integrity-control evidence."""
from __future__ import annotations

import unittest

from tools.explorer.control import control


class ControlTest(unittest.TestCase):
    def test_informative_corpus_controls(self):
        # The SALDOS and wrong-arity ALTA cases still have valid controls:
        # original log IDs 13 (E301) and 21 (E302).
        cases = (
            ("ALTA;Lucia", 82),
            ("ALTA;Mateo", 3),
            ("CONSULTA;AC-0001", 14),
            ("DEPOSITO;AC-0001;250000", 86),
            ("TRANSFER;AC-0001;AC-0002;40000", 86),
            ("CONSULTA;AC-0002", 11),
            ("TRANSFER;AC-0001;AC-0002;120000", 55),
            ("TRANSFER;AC-0001;AC-0002;100000", 12),
            ("CONSULTa;AC-0001", 14),
            ("SALDOS;AC-0001", 38),
            ("ANULA;OP-0003", 66),
            ("ANULA;OP-0003", 66),
            ("CONSULTA;AC-0009", 87),
            ("TRANSFER;AC-0002;AC-0001;50000", 23),
            ("DEPOSITO;AC-0002;700", 35),
            ("CONSULTA;AC-0002", 11),
            ("ALTA;Lucia;Gomez", 11),
        )
        for base, expected in cases:
            with self.subTest(base=base, expected=expected):
                self.assertEqual(control(base), expected)

    def test_known_invalid_control_is_not_predicted(self):
        self.assertEqual(control("ALTA;Lucia"), 82)
        self.assertNotEqual(control("ALTA;Lucia"), 83)

    def test_output_uses_unreduced_98_minus_remainder(self):
        # 65 * 100 ≡ 1 (mod 97), so the output is 97, not zero.
        self.assertEqual(control("65"), 97)
        self.assertEqual(control("32"), 2)
        self.assertEqual(control("ALTA;BZ"), 97)
        self.assertEqual(control("ALTA;HD"), 98)
        for base in ("65", "32", "ALTA;BZ", "ALTA;HD"):
            with self.subTest(base=base):
                self.assertTrue(2 <= control(base) <= 98)

    def test_composed_accent_is_filtered_without_normalization(self):
        self.assertEqual(control("ALTA;Ána"), 61)

    def test_decomposed_accent_keeps_ascii_letter_and_filters_mark(self):
        self.assertEqual(control("ALTA;A\u0308na"), 50)
        self.assertEqual(control("ALTA;Ana"), 50)

    def test_non_ascii_is_filtered_before_ascii_case_mapping(self):
        self.assertEqual(control("ALTA;ßa"), 62)
        self.assertEqual(control("ALTA;ıa"), 62)
        self.assertEqual(control("ALTA;SSA"), 40)
        self.assertEqual(control("ALTA;IA"), 77)

    def test_long_input_uses_streaming_modulo(self):
        count = 10_000
        # A maps to the decimal digit 1. Compute the repeated-digit remainder
        # without constructing or parsing the corresponding giant integer.
        encoded_remainder = sum(pow(10, i, 97) for i in range(count)) % 97
        expected = 98 - encoded_remainder * 100 % 97
        self.assertEqual(control("A" * count), expected)


if __name__ == "__main__":
    unittest.main()
