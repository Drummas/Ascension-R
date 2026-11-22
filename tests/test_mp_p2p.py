#!/usr/bin/env python3
"""scripts/mp_p2p.py, the node of multiplayer with no host (docs/notes/2026-11-22-multiplayer-phase6.md).

Nodes on 127.0.0.1 (no LAN, no DHT: they are told of each other), each with a made-up game: its matchmaker client
(tests/test_mp_sam.py's) and its signaling client (ps3recomp's tools/test_np_signaling_server.py). Two games that
search meet in one world, the same on both, the smaller id's player the host; an activation crosses the nodes with
each node's address put in; a datagram the runtime relays goes through both nodes; of three players searching for
a two-player mode two meet and the third waits; a game that stops searching is left out.

Usage:
    python tests/test_mp_p2p.py
"""
import socket
import struct
import sys
import time
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
import test_np_signaling_server as sig_t  # noqa: E402


def peer(p):
    return sig_t.peer(p)


class P2P(unittest.TestCase):
    def setUp(self):
        self.lines = []

    def node(self, name, p2p=3658):
        n = mp_p2p.Node(name, lambda t: self.lines.append("%s %s" % (name, t)), p2p_port=p2p, node_port=0, lan=False,
                        dht=False, quick_wait=0.5)
        r = mp_p2p.Running(n, sam_port=0, geo_port=0, sig_port=0)
        self.addCleanup(r.stop)
        return r

    def link(self, *nodes):
        for a in nodes:
            for b in nodes:
                if a is not b:
                    a.call(a.node.contact, ("127.0.0.1", b.ports[3]))
        end = time.time() + 5
        while time.time() < end:
            if all(len(n.call(lambda n=n: dict(n.node.peers))) == len(nodes) - 1 for n in nodes):
                return
            time.sleep(0.05)
        self.fail("the nodes did not meet: %s" % self.lines)

    def game(self, r, account, name):
        g = sam_t.Player(r.ports[0], account, name)
        self.addCleanup(g.close)
        g.sign_in()
        g.open_match()
        return g

    def signaling(self, r, name, p2p):
        c = sig_t.Client(r.ports[2], name, p2p)
        self.addCleanup(c.close)
        kind, p = c.recv()
        self.assertEqual(kind, nss.WELCOME)
        c.token = struct.unpack(">I", p[4:8])[0]
        return c

    def two_in_a_world(self):
        a, b = self.node("PlayerA"), self.node("PlayerB", 3659)
        self.link(a, b)
        ga, gb = self.game(a, 11, "PlayerA"), self.game(b, 22, "PlayerB")
        ga.search(2, 4, 4)            # Quick Play suggesting TFR4: two players meet in a mode for two after the wait
        gb.search(2, 4, 4)
        wa = sam_t.reserved(ga.recv_kind(mp_sam.WORLD_RESERVED, timeout=15))
        wb = sam_t.reserved(gb.recv_kind(mp_sam.WORLD_RESERVED, timeout=15))
        return a, b, wa, wb

    def test_two_nodes_give_their_games_one_world(self):
        a, b, wa, wb = self.two_in_a_world()
        self.assertEqual(wa, wb)                                   # one world: id, head, players, order
        wid, result, head, players = wa
        self.assertIn(head[0x10], (10, 6))                         # a mode for two
        self.assertEqual(len(players), 2)
        lead = "PlayerA" if a.node.id < b.node.id else "PlayerB"
        host = [mp_sam.online_id(e) for e in players if e[0x62] == 1]
        self.assertEqual(host, [lead])                             # the leader's player hosts
        self.assertEqual([e[0x68] for e in players], [0, 1])

    def test_signaling_and_the_relay_cross_the_nodes(self):
        a, b, _, _ = self.two_in_a_world()
        sa, sb = self.signaling(a, "PlayerA", 3658), self.signaling(b, "PlayerB", 3659)
        sa.send(nss.ACTIVATE, nss.oid("PlayerB"))
        self.assertEqual(peer(sa.recv()[1]), ("PlayerB", 1, "127.0.0.1", 3659))   # B's node as A's node sees it
        kind, p = sb.recv()
        self.assertEqual((kind, sig_t.endpoint(p)), (nss.ACTIVATED, ("PlayerA", "127.0.0.1", 3658)))
        sb.send(nss.ACTIVATE, nss.oid("PlayerA"))
        self.assertEqual(peer(sb.recv()[1])[:2], ("PlayerA", 1))
        self.assertEqual(sa.recv()[0], nss.ACTIVATED)

        # The games' P2P sockets probe their nodes; A's runtime then relays a datagram to B.
        socks = {}
        for r, c, name in ((a, sa, "PlayerA"), (b, sb, "PlayerB")):
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.bind(("127.0.0.1", 0))
            u.settimeout(5)
            self.addCleanup(u.close)
            u.sendto(nss.UDP_MAGIC + bytes([nss.U_PROBE]) + nss.oid(name) + struct.pack(">I", c.token),
                     ("127.0.0.1", r.ports[2]))
            self.assertEqual(u.recvfrom(256)[0][4], nss.U_PROBE_REPLY)
            socks[name] = u
        socks["PlayerA"].sendto(nss.UDP_MAGIC + bytes([nss.U_RELAY]) + nss.oid("PlayerB") + b"game data",
                                ("127.0.0.1", a.ports[2]))
        data, _ = socks["PlayerB"].recvfrom(256)
        self.assertEqual(data, nss.UDP_MAGIC + bytes([nss.U_RELAYED]) + nss.oid("PlayerA") + b"game data")

        sa.close()                                                 # A's game leaves: B hears it
        kind, p = sb.recv()
        self.assertEqual((kind, p[:7]), (nss.GONE, b"PlayerA"))

    def test_three_searching_for_two_two_meet(self):
        rs = [self.node("Player%s" % c, 3658 + i) for i, c in enumerate("ABC")]
        self.link(*rs)
        games = [self.game(r, 11 * (i + 1), "Player%s" % c) for i, (r, c) in enumerate(zip(rs, "ABC"))]
        for g in games:
            g.search(10, 2, 2)
        got = {}
        end = time.time() + 15
        while len(got) < 2 and time.time() < end:
            for g in games:
                if g.name in got:
                    continue
                try:
                    got[g.name] = sam_t.reserved(g.recv_kind(mp_sam.WORLD_RESERVED, timeout=0.3))
                except (TimeoutError, socket.timeout):
                    pass
        self.assertEqual(len(got), 2, self.lines)
        w = list(got.values())
        self.assertEqual(w[0], w[1])
        ids = sorted((r.node.id, "Player%s" % c) for r, c in zip(rs, "ABC"))
        self.assertEqual(sorted(got), sorted(n for _, n in ids[:2]))   # the two smallest ids
        left = [g for g in games if g.name not in got][0]
        with self.assertRaises((TimeoutError, socket.timeout)):
            left.recv_kind(mp_sam.WORLD_RESERVED, timeout=1.5)

    def status(self, r):
        """The node's players file: (me line, {name: (state, how)})."""
        try:
            lines = Path(r.node.status_file).read_text(encoding="utf-8").splitlines()
        except OSError:
            return None, {}
        me = lines[0].split("\t") if lines else None
        return me, {f[3]: (f[1], f[2]) for f in (line.split("\t") for line in lines[1:]) if len(f) == 4}

    def until(self, what, seconds=8):
        end = time.time() + seconds
        while time.time() < end:
            if what():
                return True
            time.sleep(0.1)
        return False

    def test_who_is_online_and_what_they_do(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="mp-status-")
        a, b = self.node("PlayerA"), self.node("PlayerB", 3659)
        for r, n in ((a, "a.txt"), (b, "b.txt")):
            r.node.status_file = str(Path(d, n))
        self.link(a, b)
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB") == ("ready", "direct")), self.status(a))
        me, _ = self.status(a)
        self.assertEqual(me[:3], ["me", "?", "ready"])
        gb = self.game(b, 22, "PlayerB")                          # B's game in the multiplayer menu
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB", ("",))[0] == "lobby"), self.status(a))
        gb.search(10, 2, 2)
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB", ("",))[0] == "searching"), self.status(a))
        ga = self.game(a, 11, "PlayerA")
        ga.search(10, 2, 2)
        ga.recv_kind(mp_sam.WORLD_RESERVED, timeout=15)
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB", ("",))[0] == "playing" and
                                   self.status(b)[1].get("PlayerA", ("",))[0] == "playing"), (self.status(a), self.status(b)))
        gb.send(mp_sam.SESSION, struct.pack(">IB", 0, mp_sam.GAME_TRACKER))    # the match starts...
        sid = struct.unpack(">I", gb.recv_kind(mp_sam.SESSION)[:4])[0]
        gb.send(mp_sam.SESSION_END, struct.pack(">IBB", sid, mp_sam.GAME_TRACKER, 0))   # ...and ends
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB", ("",))[0] == "lobby"), self.status(a))
        gb.close()                                                 # B's game leaves the multiplayer menu
        self.assertTrue(self.until(lambda: self.status(a)[1].get("PlayerB", ("",))[0] == "ready"), self.status(a))

    def test_a_node_asked_to_stop_says_goodbye(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="mp-status-")
        a, b = self.node("PlayerA"), self.node("PlayerB", 3659)
        a.node.stop_file = str(Path(d, "node.stop"))
        b.node.status_file = str(Path(d, "b.txt"))
        self.link(a, b)
        self.assertTrue(self.until(lambda: "PlayerA" in self.status(b)[1]), self.status(b))
        Path(a.node.stop_file).write_text("")
        self.assertTrue(self.until(lambda: a.node.stopped, 3))
        self.assertTrue(self.until(lambda: "PlayerA" not in self.status(b)[1], 3), self.status(b))   # not a minute later

    def test_a_player_heard_of_then_reached_through_another(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="mp-status-")
        rr = mp_p2p.Running(mp_p2p.Node("community", lambda t: None, node_port=0, lan=False, dht=False, community=True))
        self.addCleanup(rr.stop)
        rs = []
        for name in ("PlayerA", "PlayerB"):
            n = mp_p2p.Node(name, lambda t, name=name: self.lines.append("%s %s" % (name, t)), node_port=0, lan=False,
                            dht=False, nodes=[("127.0.0.1", rr.ports[3])], direct=False,
                            status_file=str(Path(d, name + ".txt")))
            r = mp_p2p.Running(n, sam_port=0, geo_port=0, sig_port=0)
            self.addCleanup(r.stop)
            rs.append(r)
        a = rs[0]
        seen = set()

        def how():
            h = self.status(a)[1].get("PlayerB", (None, None))[1]
            seen.add(h)
            return h == "through"
        self.assertTrue(self.until(how, 15), (self.status(a), self.lines[-20:]))
        self.assertNotIn("community", self.status(a)[1])            # a community node is no player

    def test_a_game_that_stops_searching_is_left_out(self):
        a, b = self.node("PlayerA"), self.node("PlayerB", 3659)
        self.link(a, b)
        ga, gb = self.game(a, 11, "PlayerA"), self.game(b, 22, "PlayerB")
        ga.search(10, 2, 2)
        time.sleep(0.3)
        ga.close()                                                 # A's game leaves before B searches
        time.sleep(0.5)
        gb.search(10, 2, 2)
        with self.assertRaises((TimeoutError, socket.timeout)):
            gb.recv_kind(mp_sam.WORLD_RESERVED, timeout=2.5)


if __name__ == "__main__":
    unittest.main()
