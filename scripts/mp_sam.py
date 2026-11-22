"""A matchmaker of our own for God of War: Ascension's multiplayer (docs/notes/2026-11-22-multiplayer-phase2.md): the
SAM server the lobby's Quick Play connects to, enough of it to sign a player in, open the Match service and put the
players that search into one game world. The geo port only takes the request and closes, as the real one is gone.

    mp_sam.py [--host 127.0.0.1] [--port 10070] [--geo-port 10012] [--mode N] [--players N] [--solo]
              [--quick-wait S] [--log FILE]

--mode puts every Quick Play match in that game mode (10 is FVS2, two players); --players N waits for N Quick Play
players and puts them all in one world (with --mode for a count no mode is known to take, such as three); --solo
reserves a world for a lone player, which goes no further than the game's own start-up of the match. mp_local.py runs
this in its own process.

The wire: a frame is u16 length (counting itself), service u8, message u8, then the message's fields big-endian in
order, a trailing field that is zero sometimes left out. Service 0 is the connection, 1 the Match service, 2 Profile.
"""
import argparse
import asyncio
import os
import struct
import sys
import threading
import time

CONN, MATCH, PROFILE = 0, 1, 2
# (service, message)
CLIENT_CONNECT = (CONN, 0x00)        # u64 build, u64 protocol, u32 default session, u16 n, u8, u8, n bytes NP ticket
CONNECT_RESPONSE = (CONN, 0x01)      # u64 account, u32 session, u8 service, u8 response, u8 log level, u8 reason,
                                     # [u16 app version]
SESSION = (CONN, 0x02)               # u32 session (0: a new one), u8 service, [u16 app version]
SESSION_END = (CONN, 0x03)           # u32 session, u8 service, u8 reason
SEARCH = (MATCH, 0x01)               # u16 n, u8 min players, u8 max players, u8 kind, u8 flags, n bytes (Search)
WORLD_REPORT = (MATCH, 0x04)         # u32 world, u8 n, n x u64 account, n x u32, n x u8, n x u8
WORLD_RESERVED = (MATCH, 0x15)       # u32 world, u16 n, u8 result, n bytes: 0x13-byte head, players x 0x6A entries
WORLD_UPDATE = (MATCH, 0x16)         # u32 world, u16 n, n bytes: u8 players, players x 0x6A entries
SEARCH_UPDATE = (MATCH, 0x17)        # u16 n, n bytes: u8 game mode, u8 players, players x 16-byte online id

ENTRY_SEARCH = 0x62   # a player as the search sends it: u64 account, SceNpId (36 bytes), 0x26 bytes of profile, 16
ENTRY = 0x6A          # ...and in a game world, 8 bytes more from us: u8 host (1), 3 zero bytes, u16, u8 peer index, u8
QUICK = 0x40          # search head flag: the game mode is left to us (Quick Play)
# Quick Play modes seen with the players they take (min, max): the disc's playlist suggests one at random per search,
# and two players meet in a two-player mode when nothing they suggested fits them.
# 10 FVS2 (one on one), 6 THUN2 (two against the gods' minions), 2 TFR4, 4 FFR4, 1 TFR8, 3 FFR8, 5 TCTF8.
KNOWN_MODES = {10: (2, 2), 6: (2, 2), 2: (4, 4), 4: (4, 4), 1: (6, 8), 3: (6, 8), 5: (6, 8)}


def frame(kind, payload):
    return struct.pack(">HBB", len(payload) + 4, kind[0], kind[1]) + payload


def ticket_account(ticket):
    """The account id of an NP ticket 2.x: the body section's first u64 field."""
    if len(ticket) < 12:
        return 0
    sec_len = struct.unpack(">H", ticket[10:12])[0]
    i, end = 12, min(12 + sec_len, len(ticket))
    while i + 4 <= end:
        ftype, flen = struct.unpack(">HH", ticket[i:i + 4])
        if ftype == 2 and flen == 8 and i + 12 <= end:
            return struct.unpack(">Q", ticket[i + 4:i + 12])[0]
        i += 4 + flen
    return 0


def online_id(entry):
    return entry[8:24].split(b"\0")[0].decode("ascii", "replace")


class Search:
    """A Search message: the players' range and a head (u64 build, u32, u8 game mode, u8, u8 players, u8 flags) with
    each player's entry."""

    def __init__(self, conn, payload):
        n = struct.unpack(">H", payload[0:2])[0]
        self.conn = conn
        self.minp, self.maxp, self.kind, self.flags = payload[2], payload[3], payload[4], payload[5]
        blob = payload[6:6 + n]
        if len(blob) < 16:
            raise ValueError("search head %d bytes" % len(blob))
        self.build, self.x, self.mode, self.y, self.count, self.hflags = struct.unpack(">QIBBBB", blob[:16])
        self.entries = [blob[16 + i * ENTRY_SEARCH:16 + (i + 1) * ENTRY_SEARCH] for i in range(self.count)]
        if any(len(e) != ENTRY_SEARCH for e in self.entries):
            raise ValueError("search of %d players, %d bytes" % (self.count, len(blob)))
        self.quick = bool(self.hflags & QUICK)
        self.since = time.monotonic()

    def names(self):
        return [online_id(e) for e in self.entries]


def world_blob(mode, searches):
    """A reserved world's players: 16 bytes of ours, the game mode, the count, flags 0; each player's entry with the
    host flag on the first and every player its own peer index."""
    rows = []
    for e in (e for s in searches for e in s.entries):
        slot = len(rows)
        rows.append(e + struct.pack(">BBBBHBB", 1 if slot == 0 else 0, 0, 0, 0, 0, slot, 0))
    return os.urandom(16) + bytes([mode, len(rows), 0]) + b"".join(rows)


class Matchmaker:
    def __init__(self, mode=None, solo=False, quick_wait=5.0, log=print, players=None):
        self.force_mode = mode
        self.solo = solo
        self.players = players   # Quick Play: one world for this many players, none before
        self.quick_wait = quick_wait
        self.log = log
        self.queue = []
        self.modes = dict(KNOWN_MODES)
        self.next_session = 1000
        self.next_world = 7000
        self.worlds = {}
        self.clients = set()

    def session_id(self):
        self.next_session += 1
        return self.next_session

    def waiting_with(self, s):
        if s.quick:
            return [q for q in self.queue if q.quick and q.build == s.build]
        return [q for q in self.queue if not q.quick and (q.mode, q.build) == (s.mode, s.build)]

    def pick_mode(self, group, late):
        """The game mode for these players, or None to wait for more."""
        players = sum(q.count for q in group)
        least = self.players if self.players and group[0].quick else 2
        if self.force_mode is not None:
            return self.force_mode if (self.solo or players >= least) else None
        if self.solo:
            return group[-1].mode
        if players < least:
            return None
        if not group[0].quick:
            q = group[0]
            return q.mode if q.minp <= players <= q.maxp else None
        for q in group:   # first a mode one of them suggested
            if q.minp <= players <= q.maxp:
                return q.mode
        if late:          # then any mode known to take them
            for m, (lo, hi) in self.modes.items():
                if lo <= players <= hi:
                    return m
        return None

    async def searched(self, s):
        self.queue = [q for q in self.queue if q.conn is not s.conn and not q.conn.closed]
        self.queue.append(s)
        self.modes.setdefault(s.mode, (s.minp, s.maxp))
        await self.try_match(s, late=False)
        if self.quick_wait and s.quick and s in self.queue:
            await asyncio.sleep(self.quick_wait)
            if s in self.queue:
                await self.try_match(s, late=True)

    async def try_match(self, s, late):
        group = self.waiting_with(s)
        if self.players and s.quick:
            group = first_players(group, self.players)
        players = sum(q.count for q in group)
        mode = self.pick_mode(group, late)
        self.log("   waiting (%s): %s; mode %s" % ("Quick Play" if s.quick else "mode %d" % s.mode,
                                                   [n for q in group for n in q.names()],
                                                   "to wait for" if mode is None else mode))
        ids = b"".join(e[8:24] for q in group for e in q.entries)
        for q in group:
            q.conn.send(SEARCH_UPDATE, struct.pack(">H", 2 + len(ids)) + bytes([s.mode if mode is None else mode,
                                                                                 players]) + ids)
        if mode is not None:
            self.reserve(group, mode)

    def reserve(self, group, mode):
        self.next_world += 1
        wid = self.next_world
        blob = world_blob(mode, group)
        for q in group:
            q.conn.send(WORLD_RESERVED, struct.pack(">IHB", wid, len(blob), 0) + blob)
            q.conn.world = wid
        self.worlds[wid] = group
        self.queue = [q for q in self.queue if q not in group]
        self.log("   world %d, mode %d: %s" % (wid, mode, [n for q in group for n in q.names()]))

    def gone(self, conn):
        self.queue = [q for q in self.queue if q.conn is not conn]


def first_players(group, n):
    """The searches, oldest first, that make up the first n players (a search can bring several)."""
    out, count = [], 0
    for q in group:
        if count >= n:
            break
        out.append(q)
        count += q.count
    return out


class Client:
    def __init__(self, mm, reader, writer):
        self.mm, self.r, self.w = mm, reader, writer
        self.peer = writer.get_extra_info("peername")
        self.account = 0
        self.closed = False
        self.world = 0
        self.sessions = {}
        mm.clients.add(self)

    def send(self, kind, payload):
        data = frame(kind, payload)
        self.mm.log("  -> %02x %02x %d bytes: %s" % (kind[0], kind[1], len(data), data[:48].hex(" ")))
        if not self.closed:
            self.w.write(data)

    async def run(self):
        self.mm.log("SAM connection from %s:%d" % self.peer[:2])
        try:
            while True:
                n = struct.unpack(">H", await self.r.readexactly(2))[0]
                if n < 4:
                    break
                body = await self.r.readexactly(n - 2)
                kind, payload = (body[0], body[1]), body[2:]
                self.mm.log("<- %02x %02x %d bytes: %s" % (kind[0], kind[1], n, body[:46].hex(" ")))
                await self.handle(kind, payload)
                await self.w.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.closed = True
            self.mm.gone(self)
            self.mm.clients.discard(self)
            self.mm.log("SAM connection from %s:%d closed" % self.peer[:2])
            self.w.close()

    async def handle(self, kind, p):
        if kind == CLIENT_CONNECT:
            build, proto, _, n = struct.unpack(">QQIH", p[0:22])
            self.account = ticket_account(p[24:24 + n])
            self.mm.log("   connect: build %016x protocol %d account %d" % (build, proto, self.account))
            self.send(CONNECT_RESPONSE, struct.pack(">QIBBBB", self.account, 0, 0, 0, 0, 0))
        elif kind == SESSION:
            _, service = struct.unpack(">IB", p[0:5])
            sid = self.mm.session_id()
            self.sessions[service] = sid
            self.mm.log("   session %d for service %d" % (sid, service))
            self.send(SESSION, struct.pack(">IBH", sid, service, 1))
        elif kind == SESSION_END:
            # Not answered: the game has dropped the session by then, and an answer is "session id mismatch".
            sid, service, reason = struct.unpack(">IBB", p[0:6])
            self.sessions.pop(service, None)
            if service == MATCH:
                self.mm.gone(self)
            self.mm.log("   session %d for service %d ended (reason %d)" % (sid, service, reason))
        elif kind == SEARCH:
            s = Search(self, p)
            self.mm.log("   search: %s players %d..%d, mode %d%s" % (s.names(), s.minp, s.maxp, s.mode,
                                                                    " (Quick Play)" if s.quick else ""))
            asyncio.ensure_future(self.mm.searched(s))
        elif kind == WORLD_REPORT:
            wid, n = struct.unpack(">IB", p[0:5])
            accounts = struct.unpack(">%dQ" % n, p[5:5 + 8 * n])
            self.mm.log("   world %d report: %s" % (wid, accounts))
        else:
            self.mm.log("   not handled")


async def geo(reader, writer):
    try:
        await asyncio.wait_for(reader.read(4096), 3)
    except (asyncio.TimeoutError, ConnectionError):
        pass
    writer.close()


class Running:
    """The servers on an event loop of their own (a thread); ports the ones they took."""

    def __init__(self, host, port, geo_port, mm):
        self.loop = asyncio.new_event_loop()
        self.mm = mm
        self.ports = None
        ready = threading.Event()
        self.error = None

        async def start():
            s1 = await asyncio.start_server(lambda r, w: Client(mm, r, w).run(), host, port)
            s2 = await asyncio.start_server(geo, host, geo_port)
            self.servers = (s1, s2)
            self.ports = (s1.sockets[0].getsockname()[1], s2.sockets[0].getsockname()[1])

        def run():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(start())
            except OSError as e:
                self.error = e
                ready.set()
                return
            ready.set()
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(10)
        if self.error:
            raise self.error

    def stop(self):
        async def shut():
            for s in self.servers:
                s.close()
            for c in list(self.mm.clients):
                c.w.close()
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.05)
        try:
            asyncio.run_coroutine_threadsafe(shut(), self.loop).result(5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
            if not self.thread.is_alive():
                self.loop.close()


def start(host="127.0.0.1", port=10070, geo_port=10012, mode=None, solo=False, quick_wait=5.0, log=print, players=None):
    return Running(host, port, geo_port, Matchmaker(mode, solo, quick_wait, log, players))


def main(argv):
    ap = argparse.ArgumentParser(description="God of War: Ascension's matchmaker (SAM), ours.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10070)
    ap.add_argument("--geo-port", type=int, default=10012)
    ap.add_argument("--mode", type=int, help="the game mode of every Quick Play match")
    ap.add_argument("--players", type=int, help="Quick Play waits for this many players: one world for all")
    ap.add_argument("--solo", action="store_true", help="a world for one player")
    ap.add_argument("--quick-wait", type=float, default=5.0,
                    help="seconds Quick Play players wait for a mode they suggested before any mode that takes them")
    ap.add_argument("--log", help="also write the log here")
    a = ap.parse_args(argv)
    out = open(a.log, "a", encoding="utf-8") if a.log else None

    def log(text):
        line = time.strftime("%H:%M:%S ") + text
        print(line, flush=True)
        if out:
            out.write(line + "\n")
            out.flush()

    srv = start(a.host, a.port, a.geo_port, a.mode, a.solo, a.quick_wait, log, a.players)
    log("matchmaker on %s: SAM %d, geo %d" % (a.host, srv.ports[0], srv.ports[1]))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
