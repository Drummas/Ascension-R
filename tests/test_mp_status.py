#!/usr/bin/env python3
"""scripts/mp_status.py, the website's count of the players online (docs/notes/2026-11-23-online-status.md).

Its key is the one the nodes announce (mp_p2p.KEY). On a made-up DHT on 127.0.0.1 (tests/test_mp_dht.py's), three
nodes announce under that key, two of them from one address, and one under another key: the count is two addresses,
three announces. With no DHT node answering, the status says it could not count. The JSON holds counts alone.

Usage:
    python tests/test_mp_status.py
"""
import asyncio
import datetime
import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ps3recomp" / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import mp_dht  # noqa: E402
import mp_p2p  # noqa: E402
import mp_status  # noqa: E402
import test_mp_dht as dht_t  # noqa: E402

WHEN = datetime.datetime(2026, 11, 23, 8, 20, 5, 123456, tzinfo=datetime.timezone.utc)


class Status(unittest.TestCase):
    def test_the_nodes_key(self):
        self.assertEqual(mp_status.KEY, mp_p2p.KEY)

    def test_a_count(self):
        async def run():
            net = await dht_t.network(10)
            boot = (net[0].addr,)
            for port in (40001, 40002, 40003):
                c = await dht_t.client(boot=boot)
                await c.dht.lookup(mp_status.KEY, announce_port=port, implied=False)
            other = await dht_t.client(boot=boot)
            await other.dht.lookup(mp_dht.key("another game"), announce_port=40004, implied=False)
            return await mp_status.check(boot=boot, private=True, time_limit=10.0, now=WHEN)
        s = asyncio.run(run())
        # Every client is 127.0.0.1: three announces from one address.
        self.assertEqual(s, {"format": 1, "checked": "2026-11-23T08:20:05Z", "ok": True, "players": 1,
                             "announced": 3, "dht_nodes": s["dht_nodes"]})
        self.assertGreater(s["dht_nodes"], 0)

    def test_no_dht_node_answers(self):
        quiet = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        quiet.bind(("127.0.0.1", 0))
        self.addCleanup(quiet.close)
        s = asyncio.run(mp_status.check(boot=(quiet.getsockname(),), private=True, time_limit=3.0, now=WHEN))
        self.assertEqual(s, {"format": 1, "checked": "2026-11-23T08:20:05Z", "ok": False, "players": None,
                             "announced": None, "dht_nodes": 0})


if __name__ == "__main__":
    unittest.main()
