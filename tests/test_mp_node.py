#!/usr/bin/env python3
"""scripts/mp_node.py, what the game starts for the launcher's Multiplayer (docs/notes/2026-11-22-multiplayer-phase5.md).

join and host build the TSS and write game.env with every variable the node decides (the ones a run leaves out
empty, so they are cleared); host has its servers up before game.env appears; a name the runtime would change, a
missing executable or a taken port stops it with node.error. The TSS's cipher is a stand-in here: the real one comes
from the player's GOWA.elf.

Usage:
    python tests/test_mp_node.py
"""
import os
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mp_node  # noqa: E402


class Identity:
    def encrypt(self, left, right):
        return left, right


def env_of(folder):
    out = {}
    for line in Path(folder, mp_node.ENV_FILE).read_text(encoding="utf-8").splitlines():
        k, v = line.split("=", 1)
        out[k] = v
    return out


class Node(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mp-node-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.real_elf = elf = mp_node.mp_tss.Elf
        cipher = mp_node.mp_tss.cipher
        self.addCleanup(setattr, mp_node.mp_tss, "Elf", elf)
        self.addCleanup(setattr, mp_node.mp_tss, "cipher", cipher)
        mp_node.mp_tss.Elf = lambda path: path
        mp_node.mp_tss.cipher = lambda elf: (Identity(), bytes(8))

    def error(self):
        return Path(self.dir, mp_node.ERROR_FILE).read_text(encoding="utf-8").strip()

    def test_online_ids(self):
        for name in ("Kratos", "abc", "Player-1_x", "A" * 16):
            self.assertEqual(mp_node.clean_online_id(name), name)
        for name in ("", "ab", "1abc", "_abc", "A" * 17, "Kra tos", "Kratós", None):
            self.assertIsNone(mp_node.clean_online_id(name))

    def test_join(self):
        rc = mp_node.main(["join", "--server", "127.0.0.1", "--name", "PlayerA", "--elf", "x.elf", "--dir", self.dir,
                           "--relay", "--p2p-port", "3700"])
        self.assertEqual(rc, 0)
        env = env_of(self.dir)
        self.assertEqual(list(env), list(mp_node.MANAGED))
        self.assertEqual(env["PS3_NP_SIGNALING_SERVER"], "127.0.0.1:36101")
        self.assertEqual((env["PS3_NP_ONLINE_ID"], env["PS3_NET_P2P_PORT"], env["PS3_NP_SIGNALING_RELAY"]),
                         ("PlayerA", "3700", "1"))
        self.assertEqual((env["PS3_NET_HOSTS"], env["PS3_NET_LOOPBACK_ONLY"], env["PS3_NET_ALLOW"]),
                         ("*=127.0.0.1", "1", ""))
        self.assertEqual(env["PS3_NP_TSS_FILE"], os.path.join(self.dir, "tss.bin"))
        self.assertEqual(env["PS3_NP_TUS_DIR"], os.path.join(self.dir, "np_tus"))
        self.assertGreater(os.path.getsize(os.path.join(self.dir, "tss.bin")), 0x10)
        self.assertFalse(os.path.exists(os.path.join(self.dir, mp_node.ERROR_FILE)))

    def test_a_host_elsewhere_is_let_through(self):
        lines = mp_node.env_lines("11.22.33.44", "t.bin", "tus", "PlayerB")
        env = dict(line.split("=", 1) for line in lines)
        self.assertEqual((env["PS3_NET_ALLOW"], env["PS3_NET_HOSTS"]), ("11.22.33.44", "*=11.22.33.44"))
        self.assertEqual((env["PS3_NET_P2P_PORT"], env["PS3_NP_SIGNALING_RELAY"]), ("", ""))   # cleared

    def test_a_name_the_runtime_would_change_stops_it(self):
        rc = mp_node.main(["join", "--server", "127.0.0.1", "--name", "Kra tos", "--elf", "x", "--dir", self.dir])
        self.assertEqual(rc, 2)
        self.assertIn("not an online id", self.error())
        self.assertFalse(os.path.exists(os.path.join(self.dir, mp_node.ENV_FILE)))

    def test_no_server_to_join(self):
        self.assertEqual(mp_node.main(["join", "--name", "PlayerA", "--elf", "x", "--dir", self.dir]), 2)
        self.assertIn("no server", self.error())

    def test_the_executable_it_cannot_read(self):
        mp_node.mp_tss.Elf = self.real_elf
        rc = mp_node.main(["host", "--name", "PlayerA", "--elf", os.path.join(self.dir, "none.elf"), "--dir", self.dir])
        self.assertEqual(rc, 2)
        self.assertIn("none.elf", self.error())

    def test_host_has_its_servers_up_before_game_env(self):
        ports = []
        for _ in range(2):
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            ports.append(s.getsockname()[1])
            s.close()
        self.addCleanup(setattr, mp_node, "SAM_PORT", mp_node.SAM_PORT)
        self.addCleanup(setattr, mp_node, "GEO_PORT", mp_node.GEO_PORT)
        self.addCleanup(setattr, mp_node, "SIGNALING_PORT", mp_node.SIGNALING_PORT)
        mp_node.SAM_PORT, mp_node.GEO_PORT, mp_node.SIGNALING_PORT = ports[0], ports[1], 0
        seen = []

        def wait():
            seen.append(Path(self.dir, mp_node.ENV_FILE).exists())
            with socket.create_connection(("127.0.0.1", ports[0]), timeout=3):   # the matchmaker answers
                seen.append(True)

        a = mp_node.argparse.Namespace(mode=None, players=None, dir=self.dir)
        self.assertEqual(mp_node.host(a, lambda t: None, ["X=1"], wait=wait), 0)
        self.assertEqual(seen, [True, True])

    def test_auto_runs_the_node_and_tells_the_game_its_ports(self):
        self.addCleanup(setattr, mp_node, "P2P", mp_node.P2P)
        mp_node.P2P = {"lan": False, "dht": False, "node_port": 0}
        seen = {}

        async def wait(node):
            seen["env"] = env_of(self.dir)
            seen["ports"] = node.ports
            seen["p2p"] = node.p2p_port

        a = mp_node.argparse.Namespace(name="PlayerA", elf="x.elf", dir=self.dir, relay=False, p2p_port=None)
        self.assertEqual(mp_node.auto(a, "PlayerA", lambda t: None, wait=wait), 0)
        env, ports = seen["env"], seen["ports"]
        self.assertEqual(env["PS3_NP_SIGNALING_SERVER"], "127.0.0.1:%d" % ports[2])   # the node's own, whatever port
        self.assertEqual(env["PS3_NET_HOSTS"], "*=127.0.0.1")
        self.assertEqual(env["PS3_NET_P2P_PORT"], str(seen["p2p"]))
        self.assertGreaterEqual(seen["p2p"], 3658)
        self.assertEqual(env["PS3_NP_ONLINE_ID"], "PlayerA")

    def test_a_taken_port_stops_the_host(self):
        s = socket.socket()
        s.bind(("0.0.0.0", 0))
        s.listen()
        self.addCleanup(s.close)
        self.addCleanup(setattr, mp_node, "SAM_PORT", mp_node.SAM_PORT)
        mp_node.SAM_PORT = s.getsockname()[1]
        a = mp_node.argparse.Namespace(mode=None, players=None, dir=self.dir)
        with self.assertRaises(mp_node.Stop) as e:
            mp_node.host(a, lambda t: None, ["X=1"], wait=lambda: None)
        self.assertIn("taken", str(e.exception))
        self.assertFalse(os.path.exists(os.path.join(self.dir, mp_node.ENV_FILE)))


if __name__ == "__main__":
    unittest.main()
