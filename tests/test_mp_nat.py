#!/usr/bin/env python3
"""scripts/mp_p2p.py through routers (docs/notes/2026-11-22-multiplayer-phase7.md).

Made-up routers in front of two nodes, A and B, on 127.0.0.1: a cone router keeps one outside port for every
destination, a symmetric one takes another port for each; both let in only what comes from where they sent (port and
address). A third node, R, has no router. A and B say hello to R only; R tells each of the other, introduces them,
and they punch:
- behind cone routers the hellos cross and A and B talk directly;
- behind symmetric routers nothing gets through, and after a few seconds A and B talk through R: Quick Play gives
  both the same world, and a game datagram the runtime relays goes A -> R -> B;
- A behind a router that forwards it a port (UPnP) but sends its packets out from others, as a symmetric one does:
  when A gives that port (what a node does once the router forwards it), B reaches A there and the two talk
  directly; when A does not, they are carried by R.

Usage:
    python tests/test_mp_nat.py
"""
import asyncio
import socket
import struct
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "ps3recomp" / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import mp_p2p  # noqa: E402
import mp_sam  # noqa: E402
import np_signaling_server as nss  # noqa: E402
import test_mp_sam as sam_t  # noqa: E402


class Outside(asyncio.DatagramProtocol):
    def __init__(self, nat):
        self.nat = nat
        self.sent = set()          # where this port sent to: what it lets back in

    def connection_made(self, t):
        self.t = t

    def datagram_received(self, data, addr):
        if addr[:2] in self.sent:
            self.nat.node.received(data, addr[:2])


class Forwarded(Outside):
    """A port the router forwards to the node (UPnP): anyone gets in, and the node's answers to them go out of it."""

    def datagram_received(self, data, addr):
        self.nat.flows.add(addr[:2])
        self.nat.node.received(data, addr[:2])


class Nat:
    """A router in front of a node, standing in for the node's socket (node.t)."""

    def __init__(self, node, symmetric):
        self.node, self.symmetric = node, symmetric
        self.ports = {}            # destination (symmetric) or None (cone) -> Outside
        self.forward = None        # the port it forwards to the node, if any
        self.flows = set()         # who came in through it: answers to them go out of it

    async def forward_port(self):
        loop = asyncio.get_running_loop()
        _, self.forward = await loop.create_datagram_endpoint(lambda: Forwarded(self), local_addr=("127.0.0.1", 0))
        return self.forward.t.get_extra_info("sockname")[:2]

    async def port(self, key):
        if key not in self.ports:
            loop = asyncio.get_running_loop()
            _, proto = await loop.create_datagram_endpoint(lambda: Outside(self), local_addr=("127.0.0.1", 0))
            self.ports[key] = proto
        return self.ports[key]

    def sendto(self, data, addr):
        if self.forward is not None and addr in self.flows:
            self.forward.t.sendto(data, addr)
            return
        key = addr if self.symmetric else None
        out = self.ports.get(key)
        if out is None:           # a new mapping: made, then the packet (a router does both at once)
            asyncio.ensure_future(self.later(key, data, addr))
            return
        out.sent.add(addr)
        out.t.sendto(data, addr)

    async def later(self, key, data, addr):
        out = await self.port(key)
        out.sent.add(addr)
        out.t.sendto(data, addr)

    def get_extra_info(self, name, default=None):
        return default

    def close(self):
        for out in self.ports.values():
            out.t.close()
        if self.forward is not None:
            self.forward.t.close()


class Conn:
    """A game's matchmaker connection, as the node sees it: what it is sent."""

    def __init__(self):
        self.got = []
        self.world = 0

    def send(self, kind, payload):
        self.got.append((kind, payload))

    def worlds(self):
        return [sam_t.reserved(p) for k, p in self.got if k == mp_sam.WORLD_RESERVED]


class Local:
    """A game of the node's signaling server, as far as the relay needs one: its name and P2P socket."""

    def __init__(self, name, udp):
        self.name, self.udp, self.activated = name, udp, set()

    def send(self, kind, payload):
        pass


def search(account, name):
    return types.SimpleNamespace(build=sam_t.BUILD, quick=True, mode=10, minp=2, maxp=2, count=1,
                                 entries=[sam_t.entry(account, name)], conn=Conn())


class Routers(unittest.TestCase):
    async def three(self, symmetric, forwarded=None):
        self.lines = []
        nodes = []
        for name in ("R", "PlayerA", "PlayerB"):
            n = mp_p2p.Node(name, lambda t, name=name: self.lines.append("%s %s" % (name, t)), node_port=0, lan=False,
                            dht=False, quick_wait=0.3)
            await n.start(sam_port=0, geo_port=0, sig_port=0)
            nodes.append(n)
        r, a, b = nodes
        self.real = [a.t, b.t]     # their own sockets, unused behind the routers
        a.t, b.t = Nat(a, symmetric), Nat(b, symmetric)
        if forwarded is not None:   # A's router forwards it a port; given out or not
            door = await a.t.forward_port()
            if forwarded:
                a.forwarded, a.nat = door, "open"
        a.contact(("127.0.0.1", r.port))
        b.contact(("127.0.0.1", r.port))
        return r, a, b

    def close(self, *nodes):
        for n in nodes:
            n.close()
        for t in self.real:
            t.close()

    async def until(self, what, seconds):
        for _ in range(int(seconds * 20)):
            if what():
                return True
            await asyncio.sleep(0.05)
        return False

    def test_cone_routers_punch_through(self):
        async def run():
            r, a, b = await self.three(symmetric=False)
            try:
                met = await self.until(lambda: b.id in a.peers and a.peers[b.id].via is None and
                                       a.id in b.peers and b.peers[a.id].via is None, 15)
                self.assertTrue(met, "\n".join(self.lines))
                self.assertNotEqual(a.peers[b.id].addr, ("127.0.0.1", b.port))   # B's router's port, not B's own
            finally:
                self.close(r, a, b)
        asyncio.run(run())

    def test_symmetric_routers_go_through_the_third_node(self):
        async def run():
            r, a, b = await self.three(symmetric=True)
            try:
                met = await self.until(lambda: b.id in a.peers and a.id in b.peers and
                                       a.peers[b.id].via is not None and b.peers[a.id].via is not None, 15)
                self.assertTrue(met, "\n".join(self.lines))
                self.assertIs(a.peers[b.id].via, a.peers[r.id])
                carried = await self.until(lambda: any("carrying for nodes" in line for line in self.lines), 5)
                self.assertTrue(carried, "\n".join(self.lines))   # the first message through it may still be on its way

                sa, sb = search(11, "PlayerA"), search(22, "PlayerB")
                a.start_search(sa)
                b.start_search(sb)
                got = await self.until(lambda: sa.conn.worlds() and sb.conn.worlds(), 15)
                self.assertTrue(got, "\n".join(self.lines[-30:]))
                self.assertEqual(sa.conn.worlds(), sb.conn.worlds())

                # A's runtime relays a datagram to B: A's node -> R -> B's node -> B's game.
                u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                u.bind(("127.0.0.1", 0))
                u.setblocking(False)
                local = Local("PlayerB", u.getsockname())
                b.srv.players["playerb"] = local
                b.srv.players["playera"].activated.add(local)
                a.relay_out(a.peers[b.id], "PlayerA", "PlayerB", b"game data")
                loop = asyncio.get_running_loop()
                data = await asyncio.wait_for(loop.sock_recv(u, 256), 5)
                u.close()
                self.assertEqual(data, nss.UDP_MAGIC + bytes([nss.U_RELAYED]) + nss.oid("PlayerA") + b"game data")
            finally:
                self.close(r, a, b)
        asyncio.run(run())

    def test_a_forwarded_port_given_out_lets_a_symmetric_router_in(self):
        async def run():
            r, a, b = await self.three(symmetric=True, forwarded=True)
            try:
                met = await self.until(lambda: b.id in a.peers and a.id in b.peers and
                                       a.peers[b.id].via is None and b.peers[a.id].via is None, 15)
                self.assertTrue(met, "\n".join(self.lines))
                self.assertEqual(b.peers[a.id].addr, a.forwarded)       # B talks to A at the forwarded port
            finally:
                self.close(r, a, b)
        asyncio.run(run())

    def test_a_forwarded_port_nobody_knows_of_helps_no_one(self):
        async def run():
            r, a, b = await self.three(symmetric=True, forwarded=False)
            try:
                carried = await self.until(lambda: b.id in a.peers and a.id in b.peers and
                                           a.peers[b.id].via is not None and b.peers[a.id].via is not None, 15)
                self.assertTrue(carried, "\n".join(self.lines))
            finally:
                self.close(r, a, b)
        asyncio.run(run())

    def test_a_node_carries_a_few_pairs_at_most(self):
        n = mp_p2p.Node("R", node_port=0, lan=False, dht=False)
        peers = [mp_p2p.Peer("%016x" % i, ("127.0.0.1", 1000 + i)) for i in range(2 * mp_p2p.RELAY_PAIRS + 2)]
        for p in peers:
            n.peers[p.id] = p
        ok = [n.carry(peers[2 * i], peers[2 * i + 1]) for i in range(mp_p2p.RELAY_PAIRS + 1)]
        self.assertEqual(ok, [True] * mp_p2p.RELAY_PAIRS + [False])
        self.assertTrue(n.carry(peers[1], peers[0]))       # a pair it carries already, either way round
        n.relays = False
        self.assertFalse(n.carry(peers[0], peers[1]))


if __name__ == "__main__":
    unittest.main()
