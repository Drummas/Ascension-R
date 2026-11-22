#!/usr/bin/env python3
"""scripts/mp_play.py and mp_tss.py --server: playing through a server on another machine
(docs/notes/2026-11-22-multiplayer-phase4.md).

The game's environment points every name at the server, lets nothing else through but this PC, the server and the
peers signaling introduces, and carries the player's own id and P2P port; the TSS names the server as the
matchmaker in every MatchConfig target and as the geo service.

Usage:
    python tests/test_mp_play.py
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mp_play  # noqa: E402
import mp_tss  # noqa: E402


class GameEnv(unittest.TestCase):
    def test_a_server_elsewhere(self):
        env = mp_play.game_env({"PATH": "x", "PS3_NET_ALLOW": "1.2.3.4"}, "11.22.33.44", "tss.bin", "np_tus",
                               name="PlayerA", p2p_port=3700)
        self.assertEqual(env["PS3_NET_HOSTS"], "*=11.22.33.44")
        self.assertEqual(env["PS3_NET_LOOPBACK_ONLY"], "1")
        self.assertEqual(env["PS3_NET_ALLOW"], "11.22.33.44")            # only the server, not what was there before
        self.assertEqual(env["PS3_NP_SIGNALING_SERVER"], "11.22.33.44:36101")
        self.assertEqual((env["PS3_NP_ONLINE_ID"], env["PS3_NET_P2P_PORT"]), ("PlayerA", "3700"))
        self.assertEqual((env["PS3_NP_TSS_FILE"], env["PS3_NP_TUS_DIR"], env["PS3_NP_TEST_TICKET"]),
                         ("tss.bin", "np_tus", "1"))
        self.assertNotIn("PS3_NP_SIGNALING_RELAY", env)
        self.assertEqual(env["PATH"], "x")

    def test_this_pc(self):
        env = mp_play.game_env({"PS3_NP_ONLINE_ID": "old", "PS3_NP_SIGNALING_RELAY": "1"}, "127.0.0.1", "t", "u",
                               signaling_port=36200)
        self.assertNotIn("PS3_NET_ALLOW", env)                          # loopback passes the guard anyway
        self.assertNotIn("PS3_NP_ONLINE_ID", env)                       # the launcher's or the OS login
        self.assertNotIn("PS3_NP_SIGNALING_RELAY", env)
        self.assertEqual(env["PS3_NP_SIGNALING_SERVER"], "127.0.0.1:36200")

    def test_relay_always(self):
        self.assertEqual(mp_play.game_env({}, "127.0.0.1", "t", "u", relay=True)["PS3_NP_SIGNALING_RELAY"], "1")

    def test_server_address(self):
        self.assertEqual(mp_play.server_address("192.168.1.50"), "192.168.1.50")
        self.assertEqual(mp_play.server_address("localhost"), "127.0.0.1")


class TssServer(unittest.TestCase):
    def test_every_target_and_geo_name_the_server(self):
        blocks = mp_tss.read_folder(str(ROOT / "online" / "tss"))
        out = mp_tss.with_server(blocks, "192.168.1.50", 10080, 10013)
        self.assertEqual([n for n, _, _ in out], [n for n, _, _ in blocks])
        mc = json.loads([t for n, _, t in out if n == "MatchConfig"][0])["MatchConfig"]
        targets = [mc[k] for k in sorted(mc) if k.startswith("target")]
        self.assertGreaterEqual(len(targets), 4)
        for t in targets:
            self.assertEqual((t["SAMServerHostAddr"], t["SAMServerPort"]), ("192.168.1.50", 10080))
        self.assertEqual((mc["GeoServerAddr"], mc["GeoPort"]), ("192.168.1.50", 10013))
        self.assertEqual(targets[0]["RangeHigh"], 0x7FFFFFFFFFFFFFFF)   # the big numbers stay exact
        others = [(n, t) for n, _, t in out if n != "MatchConfig"]
        self.assertEqual(others, [(n, t) for n, _, t in blocks if n != "MatchConfig"])


if __name__ == "__main__":
    unittest.main()
