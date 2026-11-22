#!/usr/bin/env python3
"""scripts/mp_dht.py, the multiplayer node's DHT client (docs/notes/2026-11-22-multiplayer-phase6.md).

bencode both ways; lookups against a made-up DHT of a dozen nodes on 127.0.0.1 (each knows all the others, answers
get_peers with the closest ones and what was announced under the key, takes announce_peer with its token, and says
where the asker is from): what one client announces another finds, a client learns its own address, and the nodes
that answered are kept, so a lookup with no bootstrap name starts from them.

Usage:
    python tests/test_mp_dht.py
"""
import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mp_dht  # noqa: E402


class FakeNode(asyncio.DatagramProtocol):
    def __init__(self, net):
        self.net = net
        self.id = os.urandom(20)
        self.store = {}
        self.secret = os.urandom(4)

    def connection_made(self, t):
        self.t = t
        self.addr = t.get_extra_info("sockname")[:2]

    def token(self, addr):
        return hashlib.sha1(self.secret + addr[0].encode()).digest()[:4]

    def datagram_received(self, data, addr):
        m = mp_dht.bdecode(data)
        q, a, t = m[b"q"], m[b"a"], m[b"t"]
        r = {"id": self.id}
        if q == b"get_peers":
            ih = a[b"info_hash"]
            close = sorted(self.net, key=lambda n: mp_dht.distance(n.id, ih))[:8]
            r["nodes"] = b"".join(n.id + mp_dht.compact(*n.addr) for n in close)
            r["token"] = self.token(addr)
            if self.store.get(ih):
                r["values"] = [mp_dht.compact(*p) for p in sorted(self.store[ih])]
        elif q == b"announce_peer":
            if a.get(b"token") != self.token(addr):
                self.t.sendto(mp_dht.bencode({"t": t, "y": "e", "e": [203, "bad token"]}), addr)
                return
            port = addr[1] if a.get(b"implied_port") else a[b"port"]
            self.store.setdefault(a[b"info_hash"], set()).add((addr[0], port))
        self.t.sendto(mp_dht.bencode({"t": t, "y": "r", "r": r, "ip": mp_dht.compact(*addr)}), addr)


class Client(asyncio.DatagramProtocol):
    def __init__(self, **kw):
        self.kw = kw

    def connection_made(self, t):
        self.t = t
        self.addr = t.get_extra_info("sockname")[:2]
        self.dht = mp_dht.Dht(lambda data, addr: t.sendto(data, addr), private=True, **self.kw)

    def datagram_received(self, data, addr):
        self.dht.received(data, addr)


async def network(n):
    loop = asyncio.get_running_loop()
    net = []
    for _ in range(n):
        node = FakeNode(net)
        await loop.create_datagram_endpoint(lambda node=node: node, local_addr=("127.0.0.1", 0))
        net.append(node)
    return net


async def client(**kw):
    loop = asyncio.get_running_loop()
    _, c = await loop.create_datagram_endpoint(lambda: Client(**kw), local_addr=("127.0.0.1", 0))
    return c


class Bencode(unittest.TestCase):
    def test_both_ways(self):
        v = {"t": b"aa", "y": "q", "a": {"id": b"\x01" * 20, "port": 6881, "ro": True}, "l": [1, b"x", []]}
        data = mp_dht.bencode(v)
        self.assertTrue(data.startswith(b"d1:ad2:id"))    # keys sorted: "a" first, and in it "id"
        back = mp_dht.bdecode(data)
        self.assertEqual(back[b"a"][b"port"], 6881)
        self.assertEqual(back[b"a"][b"ro"], 1)
        self.assertEqual(back[b"l"], [1, b"x", []])

    def test_what_is_not_one_value(self):
        for bad in (b"", b"d", b"i12", b"5:abc", b"d1:ai1ee1:x", b"x", b"l" * 40 + b"e" * 40):
            with self.assertRaises(ValueError):
                mp_dht.bdecode(bad)


class Lookup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mp-dht-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_one_announces_another_finds(self):
        async def run():
            net = await network(12)
            boot = (net[0].addr,)
            ih = mp_dht.key("test key")
            a = await client(boot=boot)
            b = await client(boot=boot)
            await a.dht.lookup(ih, announce_port=1)
            self.assertEqual(a.dht.public, a.addr)                       # where the DHT sees it
            found = await b.dht.lookup(ih)
            self.assertIn(a.addr, found)                                  # implied_port: its socket's port
            self.assertNotIn((a.addr[0], 1), found)
            holders = [n for n in net if ih in n.store]
            self.assertTrue(holders)
            self.assertLessEqual(len(holders), mp_dht.K)
            self.assertFalse(a.dht.pending or b.dht.pending)
        asyncio.run(run())

    def test_a_port_given_outright(self):
        """A node whose router forwards it a port announces that one, not the one its questions come from."""
        async def run():
            net = await network(10)
            ih = mp_dht.key("test key")
            a = await client(boot=(net[0].addr,))
            b = await client(boot=(net[0].addr,))
            await a.dht.lookup(ih, announce_port=4321, implied=False)
            found = await b.dht.lookup(ih)
            self.assertIn((a.addr[0], 4321), found)
            self.assertNotIn(a.addr, found)
        asyncio.run(run())

    def test_the_nodes_that_answered_are_kept(self):
        async def run():
            net = await network(10)
            cache = os.path.join(self.dir, "dht-nodes.json")
            ih = mp_dht.key("test key")
            a = await client(boot=(net[0].addr,), cache_file=cache)
            await a.dht.lookup(ih, announce_port=1)
            self.assertTrue(os.path.getsize(cache) > 2)
            b = await client(boot=(), cache_file=cache)                   # no bootstrap name: the kept nodes
            self.assertIn(a.addr, await b.dht.lookup(ih))
        asyncio.run(run())

    def test_no_node_answers(self):
        async def run():
            c = await client(boot=(("127.0.0.1", 9),))
            self.assertEqual(await c.dht.lookup(mp_dht.key("x"), time_limit=5), set())
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
