"""Unit tests for control_probe using a token-free fake Client."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import control_probe  # noqa: E402


class FakeResult:
    def __init__(self, entry_id, status, response):
        self.id = entry_id
        self.status = status
        self.response = response


class FakeSequence:
    def __init__(self, client, seq):
        self.client, self.seq = client, seq

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def flush(self):
        self.client.entries.append({"id": self.client.next_id, "seq": self.seq})
        self.client.next_id += 1

    def msg(self, message, hypothesis, **kwargs):
        self.client.messages.append((message, hypothesis, kwargs))
        status, response = self.client.outcomes.pop(0)
        result = FakeResult(self.client.next_id, status, response)
        self.client.entries.append({"id": self.client.next_id, "seq": self.seq})
        self.client.next_id += 1
        return result


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.entries = []
        self.messages = []
        self.next_id = 1

    def used_today(self):
        return len(self.entries)

    def sequence(self, seq, _hypothesis, *, no_cache):
        assert no_cache is True
        return FakeSequence(self, seq)

    def seq_steps(self, seq):
        return [entry for entry in self.entries if entry["seq"] == seq]


class ControlProbeTest(unittest.TestCase):
    def test_continues_e202_and_stops_on_first_other_error(self):
        client = FakeClient([
            (400, {"error": "E202", "mensaje": "control inválido"}),
            (404, {"error": "E401", "mensaje": "cuenta inexistente"}),
            (200, {"ok": True}),
        ])
        result = control_probe.scan(client, "CONSULTA;AC-0017", "holdout", 7, 9)
        self.assertEqual(result["classification"], "control_passed")
        self.assertEqual([p["control"] for p in result["probes"]], [7, 8])
        self.assertEqual(result["reset_id"], 1)
        self.assertEqual(result["ids"], [2, 3])
        self.assertEqual(client.messages[0][0], "CONSULTA;AC-0017;7")
        self.assertEqual(result["used_after"] - result["used_before"], 3)

    def test_e201_marks_malformed_and_aborts_scan(self):
        client = FakeClient([
            (400, {"error": "E201", "mensaje": "control mal formado"}),
            (200, {"pong": True}),
        ])
        result = control_probe.scan(client, "PING", "malformed", 0, 1)
        self.assertEqual(result["classification"], "malformed")
        self.assertEqual(len(result["probes"]), 1)
        self.assertEqual(control_probe.exit_status(result["classification"]), 2)

    def test_auth_and_pre_integrity_errors_are_unexpected(self):
        for status, response in [
            (401, {"error": "E001"}),
            (400, {"error": "E100"}),
            (400, {"error": "E102"}),
            (404, {"error": "E404"}),
            (418, {"error": "EXTRA"}),
            (200, {"ok": True}),
        ]:
            with self.subTest(response=response):
                client = FakeClient([(status, response), (404, {"error": "E401"})])
                result = control_probe.scan(client, "CONSULTA;AC-0017", "unexpected", 0, 1)
                self.assertEqual(result["classification"], "unexpected")
                self.assertEqual(len(result["probes"]), 1)
                self.assertEqual(control_probe.exit_status(result["classification"]), 2)

    def test_trailing_semicolon_preserves_empty_argument_position(self):
        client = FakeClient([(400, {"error": "E202"})])
        control_probe.scan(client, "CONSULTA;AC-0017;", "empty-field", 6, 6)
        self.assertEqual(client.messages[0][0], "CONSULTA;AC-0017;;6")

    def test_all_e202_is_no_match_through_inclusive_stop(self):
        client = FakeClient([(400, {"error": "E202"}) for _ in range(3)])
        result = control_probe.scan(client, "CONSULTA;AC-0100", "none", 3, 5)
        self.assertEqual(result["classification"], "no_match")
        self.assertEqual([p["control"] for p in result["probes"]], [3, 4, 5])
        self.assertEqual(result["used_after"] - result["used_before"], 4)
        self.assertEqual(control_probe.exit_status(result["classification"]), 1)

    def test_pass_does_not_claim_command_succeeded(self):
        client = FakeClient([(422, {"error": "E507", "mensaje": "saldo insuficiente"})])
        result = control_probe.scan(client, "TRANSFER;AC-0017;AC-0100;12345", "oracle", 21, 21)
        self.assertEqual(result["classification"], "control_passed")
        self.assertIn("no éxito del comando", result["oracle_note"])

    def test_only_known_success_shapes_are_accepted(self):
        known = FakeClient([(200, {"cuenta_id": "AC-0017", "saldo": 0})])
        self.assertEqual(
            control_probe.scan(known, "CONSULTA;AC-0017", "known-success", 64, 64)["classification"],
            "control_passed",
        )
        unknown = FakeClient([(200, {"new": "shape"})])
        self.assertEqual(
            control_probe.scan(unknown, "PING", "unknown-success", 64, 64)["classification"],
            "unexpected",
        )

    def test_ping_response_does_not_prove_control_was_checked(self):
        client = FakeClient([(200, {"pong": True})])
        result = control_probe.scan(client, "PING", "ping-bypass", 64, 64)
        self.assertEqual(result["classification"], "unexpected")

    def test_known_post_integrity_errors_e303_and_e402(self):
        for status, error in [(400, "E303"), (404, "E402")]:
            with self.subTest(error=error):
                client = FakeClient([(status, {"error": error})])
                result = control_probe.scan(client, "ANULA;OP-0042", f"{error}-oracle", 0, 0)
                self.assertEqual(result["classification"], "control_passed")


if __name__ == "__main__":
    unittest.main()
