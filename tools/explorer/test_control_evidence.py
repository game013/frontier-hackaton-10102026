"""Check the control against captured responses and trace fixtures to the audit log."""
import base64
import json
from pathlib import Path
import unittest

from tools.explorer.control import control

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'tests/corpus/a1'


def sequences():
    return [
        [json.loads(line) for line in path.read_text().splitlines()]
        for path in sorted(CORPUS.glob('*.jsonl'))
    ]


class ControlEvidenceTest(unittest.TestCase):
    def test_formula_agrees_with_every_captured_integrity_result(self):
        captured = sequences()
        self.assertEqual(len(captured), 7)
        for sequence in captured:
            for row in sequence[1:]:
                with self.subTest(id=row['id']):
                    base, supplied = row['request']['m'].rsplit(';', 1)
                    expected = str(control(base))
                    error = row['response'].get('error')
                    if error == 'E201':
                        # Observed malformed fields in this corpus have three/four digits.
                        self.assertGreater(len(supplied), 2)
                        self.assertEqual(row['status'], 400)
                    elif error == 'E202':
                        self.assertNotEqual(supplied, expected)
                        self.assertEqual(row['status'], 400)
                    else:
                        self.assertEqual(supplied, expected)

    def test_reserved_predictions_repeat_status_and_exact_bytes(self):
        holdouts = json.loads((CORPUS / 'reserved-bases.json').read_text())
        runs = [sequence for sequence in sequences() if sequence[0]['seq'].startswith('a1-holdouts-')]
        self.assertEqual(len(runs), 2)
        self.assertEqual(len(holdouts), 9)
        for sequence in runs:
            self.assertEqual(len(sequence), 1 + len(holdouts) * 2)
            for index, base in enumerate(holdouts):
                correct, neighbor = sequence[1 + index * 2:3 + index * 2]
                expected = control(base)
                self.assertEqual(correct['request']['m'], f'{base};{expected}')
                self.assertEqual(neighbor['request']['m'], f'{base};{expected + 1}')
                self.assertNotIn(correct['response'].get('error'), ('E201', 'E202'))
                self.assertEqual(neighbor['response']['error'], 'E202')
        for first, second in zip(runs[0], runs[1]):
            for key in ('status', 'request_b64', 'response_b64'):
                self.assertEqual(first[key], second[key])

    def test_fixtures_retain_exact_bytes_ids_and_reset_context(self):
        audit_rows = [json.loads(line) for line in (ROOT / 'experimentos.jsonl').read_text().splitlines()]
        self.assertEqual([e['id'] for e in audit_rows], list(range(1, len(audit_rows) + 1)))
        audit = {e['id']: e for e in audit_rows}
        seen = set()
        for sequence in sequences():
            self.assertEqual(sequence[0]['path'], '/__reset')
            self.assertEqual(sequence[0]['status'], 200)
            for n, row in enumerate(sequence, 1):
                with self.subTest(id=row['id']):
                    self.assertEqual(row['n'], n)
                    self.assertEqual(row['seq'], sequence[0]['seq'])
                    self.assertNotIn(row['id'], seen)
                    seen.add(row['id'])
                    source = audit[row['id']]
                    self.assertEqual(source['outcome'], 'completed')
                    self.assertFalse(source.get('infrastructure'))
                    for key, value in row.items():
                        if key != 'n':
                            self.assertEqual(value, source[key])
                    self.assertEqual(json.loads(base64.b64decode(row['response_b64'])), row['response'])
                    if row['request'] is not None:
                        self.assertEqual(json.loads(base64.b64decode(row['request_b64'])), row['request'])
        self.assertEqual(len(seen), 174)


if __name__ == '__main__':
    unittest.main()
