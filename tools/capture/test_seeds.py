import json
import unittest

import seeds


def rec(n, seq, boot="b1", **kw):
    return json.dumps({"kind": "capture", "ts": f"2026-10-10T20:00:{n:02d}Z", "boot": boot, "n": n,
                       "seq": seq, "version": "v1", "method": "POST", "uri": "/msg", **kw})


class SeedsTest(unittest.TestCase):
    def test_groups_by_boot_and_seq_from_noisy_logs(self):
        lines = [
            "2026-10-10 15:00:00 [replacement] " + rec(1, 0),
            "replacement escuchando en :9900",
            rec(2, 1, body_b64="e30="),
            rec(2, 1, body_b64="e30="),  # duplicado: archivo + stdout
            "basura { no json",
            json.dumps({"kind": "otro"}),
            rec(1, 0, boot="b2"),
        ]
        got = seeds.sequences(seeds.records(lines))
        self.assertEqual([(s["boot"], s["seq"], len(s["steps"])) for s in got],
                         [("b1", 0, 1), ("b2", 0, 1), ("b1", 1, 1)])
        self.assertEqual(got[2]["steps"][0]["body_b64"], "e30=")
        self.assertEqual(got[0]["version"], "v1")


if __name__ == "__main__":
    unittest.main()
