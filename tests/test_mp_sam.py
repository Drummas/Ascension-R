#!/usr/bin/env python3
"""scripts/mp_sam.py, our matchmaker for the multiplayer (docs/notes/2026-11-22-multiplayer-phase2.md).

Clients here speak the game's side of the wire as it was recorded: sign in with a ticket, open the Match service,
search; two players meet in one game world, each with its own peer index and the first one the host.

Usage:
    python tests/test_mp_sam.py
"""
import socket
import struct
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mp_sam  # noqa: E402

BUILD = 0x2A5752D180000817


def ticket(account, name):
    """An NP ticket 2.1 as the runtime's PS3_NP_TEST_TICKET makes one: serial, issuer, two dates, account, online id."""
    fields = (struct.pack(">HH", 8, 20) + b"test".ljust(20, b"\0") + struct.pack(">HHI", 1, 4, 0x100) +
              struct.pack(">HHQ", 7, 8, 1) + struct.pack(">HHQ", 7, 8, 2) + struct.pack(">HHQ", 2, 8, account) +
              struct.pack(">HH", 4, 32) + name.encode().ljust(32, b"\0"))
    body = struct.pack(">HH", 0x3000, len(fields)) + fields
    return struct.pack(">II", 0x21010000, len(body)) + body


def entry(account, name):
    """A player as the search sends one: account, SceNpId (online id first), a profile the matchmaker passes on."""
    npid = name.encode().ljust(16, b"\0") + bytes(20)
    profile = bytes([0, 0, 0, 0, 0, 0x64, 0, 0, 0x7F, 0xFF, 0x7F, 0xFF, 0, 0, ord("u"), ord("s"), 8]).ljust(0x26, b"\0")
    e = struct.pack(">Q", account) + npid + profile + bytes(16)
    assert len(e) == mp_sam.ENTRY_SEARCH
    return e


class Player:
    def __init__(self, port, account, name):
        self.account, self.name = account, name
        self.s = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.buf = b""

    def send(self, kind, payload):
        self.s.sendall(mp_sam.frame(kind, payload))

    def recv(self, timeout=10):
        end = time.time() + timeout
        while True:
            if len(self.buf) >= 2:
                n = struct.unpack(">H", self.buf[:2])[0]
                if len(self.buf) >= n:
                    f, self.buf = self.buf[:n], self.buf[n:]
                    return (f[2], f[3]), f[4:]
            self.s.settimeout(max(0.05, end - time.time()))
            data = self.s.recv(65536)
            if not data:
                raise EOFError("closed")
            self.buf += data

    def recv_kind(self, kind, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            k, p = self.recv(max(0.05, end - time.time()))
            if k == kind:
                return p
        raise TimeoutError(kind)

    def sign_in(self):
        t = ticket(self.account, self.name)
        self.send(mp_sam.CLIENT_CONNECT, struct.pack(">QQIHBB", BUILD, 15, 0, len(t), 0, 0) + t)
        return self.recv_kind(mp_sam.CONNECT_RESPONSE)

    def open_match(self):
        self.send(mp_sam.SESSION, struct.pack(">IB", 0, mp_sam.MATCH))
        return self.recv_kind(mp_sam.SESSION)

    def search(self, mode, minp, maxp, quick=True):
        e = entry(self.account, self.name)
        head = struct.pack(">QIBBBB", BUILD, 0, mode, 0, 1, mp_sam.QUICK if quick else 0)
        blob = head + e
        self.send(mp_sam.SEARCH, struct.pack(">HBBBB", len(blob), minp, maxp, 2, 0) + blob)

    def close(self):
        self.s.close()


def reserved(payload):
    wid, n, result = struct.unpack(">IHB", payload[:7])
    blob = payload[7:7 + n]
    head, rows = blob[:0x13], blob[0x13:]
    players = [rows[i * mp_sam.ENTRY:(i + 1) * mp_sam.ENTRY] for i in range(head[0x11])]
    return wid, result, head, players


class Matchmaker(unittest.TestCase):
    def serve(self, **kw):
        self.lines = []
        srv = mp_sam.start(port=0, geo_port=0, log=self.lines.append, **kw)
        self.addCleanup(srv.stop)
        return srv.ports[0]

    def player(self, port, account, name):
        p = Player(port, account, name)
        self.addCleanup(p.close)
        return p

    def test_sign_in_answers_with_the_tickets_account(self):
        port = self.serve()
        p = self.player(port, 0x37FC4AE6182315F1, "PlayerA")
        account, session, service, response, level, reason = struct.unpack(">QIBBBB", p.sign_in())
        self.assertEqual(account, 0x37FC4AE6182315F1)
        self.assertEqual((session, service, response, level, reason), (0, 0, 0, 0, 0))

    def test_a_session_for_the_match_service(self):
        port = self.serve()
        p = self.player(port, 1, "PlayerA")
        p.sign_in()
        sid, service, appver = struct.unpack(">IBH", p.open_match())
        self.assertNotEqual(sid, 0)           # the game logs an error for session 0
        self.assertEqual(service, mp_sam.MATCH)
        self.assertEqual(appver, 1)

    def test_two_quick_play_players_meet_in_one_world(self):
        port = self.serve(quick_wait=0)
        a, b = self.player(port, 11, "PlayerA"), self.player(port, 22, "PlayerB")
        for p in (a, b):
            p.sign_in()
            p.open_match()
        a.search(10, 2, 2)
        upd = a.recv_kind(mp_sam.SEARCH_UPDATE)
        self.assertEqual(upd[3], 1)           # u16 n, then mode, players
        b.search(10, 2, 2)
        wa = reserved(a.recv_kind(mp_sam.WORLD_RESERVED))
        wb = reserved(b.recv_kind(mp_sam.WORLD_RESERVED))
        self.assertEqual(wa[0], wb[0])
        self.assertNotEqual(wa[0], 0)
        self.assertEqual(wa[1], 0)            # MatchResultCode Success
        self.assertEqual(wa[2][0x10:], bytes([10, 2, 0]))
        self.assertEqual(wa[2], wb[2])
        players = wa[3]
        self.assertEqual([struct.unpack(">Q", e[:8])[0] for e in players], [11, 22])
        self.assertEqual([e[0x68] for e in players], [0, 1])          # peer index, each its own
        self.assertEqual([e[0x62] for e in players], [1, 0])          # the host
        self.assertEqual(players[1][:mp_sam.ENTRY_SEARCH], entry(22, "PlayerB"))

    def test_quick_play_suggestions_that_do_not_fit_meet_in_a_known_mode(self):
        port = self.serve(quick_wait=0.2)
        a, b = self.player(port, 11, "PlayerA"), self.player(port, 22, "PlayerB")
        for p in (a, b):
            p.sign_in()
            p.open_match()
        a.search(5, 6, 8)
        b.search(3, 6, 8)
        wid, result, head, players = reserved(a.recv_kind(mp_sam.WORLD_RESERVED))
        self.assertEqual(head[0x10], 10)      # two players: a two-player mode
        self.assertEqual(len(players), 2)

    def test_a_forced_mode(self):
        port = self.serve(mode=6, quick_wait=0)
        a, b = self.player(port, 11, "PlayerA"), self.player(port, 22, "PlayerB")
        for p in (a, b):
            p.sign_in()
            p.open_match()
        a.search(5, 6, 8)
        b.search(10, 2, 2)
        self.assertEqual(reserved(b.recv_kind(mp_sam.WORLD_RESERVED))[2][0x10], 6)

    def test_fixed_modes_only_meet_their_own(self):
        port = self.serve(quick_wait=0)
        a, b, c = (self.player(port, i, n) for i, n in ((11, "PlayerA"), (22, "PlayerB"), (33, "PlayerC")))
        for p in (a, b, c):
            p.sign_in()
            p.open_match()
        a.search(6, 2, 2, quick=False)
        b.search(10, 2, 2, quick=False)
        time.sleep(0.3)
        c.search(6, 2, 2, quick=False)
        wid, result, head, players = reserved(c.recv_kind(mp_sam.WORLD_RESERVED))
        self.assertEqual(head[0x10], 6)
        self.assertEqual(sorted(struct.unpack(">Q", e[:8])[0] for e in players), [11, 33])
        with self.assertRaises((TimeoutError, socket.timeout)):
            b.recv_kind(mp_sam.WORLD_RESERVED, timeout=0.5)

    def test_a_player_who_leaves_is_not_matched(self):
        port = self.serve(quick_wait=0)
        a, b = self.player(port, 11, "PlayerA"), self.player(port, 22, "PlayerB")
        a.sign_in()
        a.open_match()
        a.search(10, 2, 2)
        a.recv_kind(mp_sam.SEARCH_UPDATE)
        a.close()
        time.sleep(0.3)
        b.sign_in()
        b.open_match()
        b.search(10, 2, 2)
        upd = b.recv_kind(mp_sam.SEARCH_UPDATE)
        self.assertEqual(upd[3], 1)           # alone
        with self.assertRaises((TimeoutError, socket.timeout)):
            b.recv_kind(mp_sam.WORLD_RESERVED, timeout=0.5)

    def test_solo(self):
        port = self.serve(solo=True, quick_wait=0)
        a = self.player(port, 11, "PlayerA")
        a.sign_in()
        a.open_match()
        a.search(6, 2, 2)
        wid, result, head, players = reserved(a.recv_kind(mp_sam.WORLD_RESERVED))
        self.assertEqual((head[0x10], len(players), players[0][0x62]), (6, 1, 1))

    def test_ticket_account(self):
        self.assertEqual(mp_sam.ticket_account(ticket(0x1234567890ABCDEF, "PlayerA")), 0x1234567890ABCDEF)
        self.assertEqual(mp_sam.ticket_account(b""), 0)


if __name__ == "__main__":
    unittest.main()
