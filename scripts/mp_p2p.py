"""Multiplayer with no host (docs/notes/2026-11-22-multiplayer-phase6.md): the node each player's game runs when the
launcher's Multiplayer is on Auto (scripts/mp_node.py auto).

On this PC the node is the game's matchmaker (SAM) and signaling server, as a host's node is (phase 5), but for its
own game only. With the other players' nodes it keeps a network of its own, on one UDP socket: it finds them through
the BitTorrent DHT (mp_dht.py: every node announces itself under one key and looks up the others) and, on this PC's
network, by multicast; then every node says hello to the ones it found and pings them now and then.

Quick Play: a node whose game searches tells every node it knows, again every two seconds. The node with the smallest
id among the players searching together leads: it picks the game mode as our matchmaker does (mp_sam.py), builds the
world (its own player first: the host) and proposes it; a node that is searching and not promised elsewhere accepts;
with every yes the leader commits, and every node gives its game the same world. A no or no answer ends the proposal
and the leader tries again without the node that said no.

Signaling: in a world, each other player is a RemotePlayer of the node's signaling server. Its messages
(ACTIVATED, DEACTIVATED, GONE, MOVED) go to the node it plays behind, which hands them to its game with the address
it sees our node at; datagrams the runtime relays (two games that cannot reach each other) go the same way.

Messages: UDP, b"ASCR" + 1 + JSON with the sender's id, or b"ASCR" + 2 + from (16) + to (16) + a relayed datagram.
"""
import asyncio
import base64
import json
import os
import random
import socket
import struct
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ps3recomp", "tools"))
import mp_dht  # noqa: E402
import mp_sam  # noqa: E402
import np_signaling_server as nss  # noqa: E402

MAGIC = b"ASCR"
V_JSON, V_RELAY = 1, 2
PROTOCOL = 1
KEY = mp_dht.key("ascension-r/multiplayer/%d" % PROTOCOL)   # what every node announces on the DHT
NODE_PORT = 36102
LAN_GROUP, LAN_PORT = "239.255.65.82", 36103                 # the nodes on this PC's network
PING_EVERY, PEER_TIMEOUT = 15.0, 60.0
SEARCH_EVERY, SEARCH_TIMEOUT = 2.0, 7.0
PROPOSE_TIMEOUT, LOCK_TIMEOUT, BUSY = 2.5, 4.0, 5.0
LAN_EVERY, CONTACT_AGAIN = 5.0, 30.0
DHT_EVERY, DHT_SEARCHING_EVERY = 300.0, 30.0
MAX_PLAYERS = 8


def b64(b):
    return base64.b64encode(b).decode("ascii")


def unb64(s, n=None):
    try:
        b = base64.b64decode(s, validate=True)
    except (ValueError, TypeError):
        return None
    return b if n is None or len(b) == n else None


class Peer:
    """Another player's node."""

    def __init__(self, nid, addr):
        self.id, self.addr = nid, addr
        self.name = ""
        self.last = self.pinged = time.monotonic()
        self.search = None          # its game's search while it searches (the message)
        self.search_at = 0.0
        self.busy_until = 0.0       # said no to a world, or did not answer: not proposed to before then


class RemotePlayer:
    """A player of the signaling server whose game is behind another node: its messages and the datagrams relayed to
    it go to that node, which hands them on."""
    remote = True

    def __init__(self, node, peer, name, port):
        self.node, self.peer = node, peer
        self.name, self.port = name, port
        self.ip = peer.addr[0]
        self.server_ip = "0.0.0.0"    # what a message to it says of our player's address: its node puts its own in
        self.local_ip = None
        self.udp = None
        self.token = 0
        self.activated = set()

    def send(self, kind, payload=b""):
        self.node.sig_out(self.peer, self.name, kind, payload)

    def where_for(self, viewer):
        return self.peer.addr[0], self.port

    def endpoint_for(self, viewer):
        a, port = self.where_for(viewer)
        return nss.ip4(a) + struct.pack(">H", port)

    def address_for(self, viewer):
        return self.where_for(viewer)[0]

    def relay_ready(self):
        return True

    def relayed_from(self, sender, payload, transport):
        self.node.relay_out(self.peer, sender.name, self.name, payload)


class Matchmaker(mp_sam.Matchmaker):
    """The game's matchmaker: its search goes to the node, and the world the nodes agree on comes back to it."""

    def __init__(self, node, quick_wait, log):
        super().__init__(quick_wait=quick_wait, log=log)
        self.node = node

    async def searched(self, s):
        self.queue = [s]
        self.node.start_search(s)

    def gone(self, conn):
        if self.node.local is not None and self.node.local.conn is conn:
            self.node.cancel_search("its game stopped searching")
        self.queue = [q for q in self.queue if q.conn is not conn]

    def deliver(self, q, wid, blob):
        q.conn.send(mp_sam.WORLD_RESERVED, struct.pack(">IHB", wid, len(blob), 0) + blob)
        q.conn.world = wid
        self.queue = [x for x in self.queue if x is not q]

    def update(self, q, mode, entries):
        ids = b"".join(e[8:24] for e in entries)
        q.conn.send(mp_sam.SEARCH_UPDATE, struct.pack(">H", 2 + len(ids)) + bytes([mode, len(entries)]) + ids)


class Socket(asyncio.DatagramProtocol):
    def __init__(self, node):
        self.node = node

    def connection_made(self, t):
        self.node.t = t

    def datagram_received(self, data, addr):
        self.node.received(data, addr[:2])

    def error_received(self, exc):
        pass


class Lan(asyncio.DatagramProtocol):
    def __init__(self, node):
        self.node = node

    def datagram_received(self, data, addr):
        self.node.lan_heard(data, addr[:2])

    def error_received(self, exc):
        pass


class Node:
    def __init__(self, name, log=lambda text: None, p2p_port=3658, node_port=NODE_PORT, lan=True, dht=True,
                 dht_cache=None, quick_wait=5.0, boot=None, private=False):
        self.id = os.urandom(8).hex()
        self.name, self.log, self.p2p_port = name, log, p2p_port
        self.want_port, self.use_lan, self.use_dht = node_port, lan, dht
        self.dht_cache, self.boot, self.private = dht_cache, boot, private
        self.peers = {}
        self.contacted = {}             # address -> when we last said hello there
        self.search = None              # our game's search, as the others are told it
        self.search_since = self.search_sent = 0.0
        self.local = None               # that search (mp_sam), whose connection gets the world
        self.lock = None                # {wid, leader, until, players, blob}: a world we said yes to
        self.proposal = None            # ours, while the others answer
        self.next_propose = 0.0
        self.world = None
        self.last_update = None
        self.lan_sent = 0.0
        self.t = self.lan_t = self.sig_udp = None
        self.dht = None
        self.mm = Matchmaker(self, quick_wait, log)
        self.srv = nss.Server(lambda text: log("[signaling] " + text))
        self.servers = []
        self.tasks = []

    # -- start ------------------------------------------------------------------------------------------------------

    async def start(self, sam_port=10070, geo_port=10012, sig_port=nss.DEFAULT_PORT):
        """The game's matchmaker and signaling server on this PC (each port, or any when it is taken), the node's
        socket (NODE_PORT, or any), the LAN and the DHT. The ports taken: (sam, geo, signaling, node)."""
        loop = asyncio.get_running_loop()

        async def server(handler, port):
            try:
                return await asyncio.start_server(handler, "127.0.0.1", port)
            except OSError:
                return await asyncio.start_server(handler, "127.0.0.1", 0)
        sam = await server(lambda r, w: mp_sam.Client(self.mm, r, w).run(), sam_port)
        geo = await server(mp_sam.geo, geo_port)
        sig = await server(lambda r, w: nss.Player(self.srv, r, w).run(), sig_port)
        sport = sig.sockets[0].getsockname()[1]
        self.sig_udp, _ = await loop.create_datagram_endpoint(lambda: nss.Udp(self.srv), local_addr=("127.0.0.1", sport))
        self.srv.udp_port = sport
        self.servers = [sam, geo, sig]
        try:
            await loop.create_datagram_endpoint(lambda: Socket(self), local_addr=("0.0.0.0", self.want_port))
        except OSError:
            await loop.create_datagram_endpoint(lambda: Socket(self), local_addr=("0.0.0.0", 0))
        self.port = self.t.get_extra_info("sockname")[1]
        if self.use_lan:
            await self.lan_start(loop)
        if self.use_dht:
            self.dht = mp_dht.Dht(lambda d, a: self.t.sendto(d, a), self.log, self.dht_cache,
                                  boot=self.boot or mp_dht.BOOTSTRAP, private=self.private)
            self.tasks.append(asyncio.ensure_future(self.dht_loop()))
        self.tasks.append(asyncio.ensure_future(self.ticker()))
        self.ports = (sam.sockets[0].getsockname()[1], geo.sockets[0].getsockname()[1], sport, self.port)
        self.log("node %s for %s: matchmaker %d, geo %d, signaling %d on this PC; node port %d%s%s" % (
            self.id[:8], self.name, self.ports[0], self.ports[1], sport, self.port, ", LAN" if self.use_lan else "",
            ", DHT" if self.use_dht else ""))
        return self.ports

    async def lan_start(self, loop):
        """Multicast: the nodes on this network say where they are. The listening socket shares its port with the
        other nodes on this PC."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", LAN_PORT))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                         socket.inet_aton(LAN_GROUP) + socket.inet_aton("0.0.0.0"))
            s.setblocking(False)
            self.lan_t, _ = await loop.create_datagram_endpoint(lambda: Lan(self), sock=s)
            out = self.t.get_extra_info("socket")
            out.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            out.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except OSError as e:
            self.use_lan = False
            self.log("no LAN discovery: %s" % e)

    def close(self):
        for s in self.servers:
            s.close()
        for c in list(self.mm.clients):
            c.w.close()
        for pl in list(self.srv.players.values()):
            if not getattr(pl, "remote", False):
                pl.w.close()
        for t in self.tasks:
            t.cancel()
        for t in (self.t, self.lan_t, self.sig_udp):
            if t:
                t.close()
        if self.dht:
            self.dht.save_cache()

    # -- messages ---------------------------------------------------------------------------------------------------

    def send_json(self, addr, **m):
        m["id"] = self.id
        try:
            self.t.sendto(MAGIC + bytes([V_JSON]) + json.dumps(m, separators=(",", ":")).encode(), addr)
        except (OSError, AttributeError):
            pass

    def to_all(self, **m):
        for p in list(self.peers.values()):
            self.send_json(p.addr, **m)

    def received(self, data, addr):
        if data[:1] == b"d":
            if self.dht:
                self.dht.received(data, addr)
            return
        if len(data) < 5 or data[:4] != MAGIC:
            return
        if data[4] == V_RELAY:
            self.relay_in(data[5:], addr)
            return
        if data[4] != V_JSON:
            return
        try:
            m = json.loads(data[5:])
        except ValueError:
            return
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or m["id"] == self.id:
            return
        t = m.get("t")
        if t == "hello":
            self.hello_in(m, addr)
            return
        p = self.peers.get(m["id"])
        if p is None:
            self.contact(addr)                       # a node that knows us and we not it: hello (now and then)
            return
        p.last = time.monotonic()
        if p.addr != addr:                          # its router gave it another port
            self.log("node %s now at %s:%d" % ((p.id[:8],) + addr))
            p.addr = addr
        handler = getattr(self, "on_" + str(t), None)
        if handler:
            try:
                handler(p, m)
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                self.log("node %s: %s message not understood (%s)" % (p.id[:8], t, e))

    def contact(self, addr):
        now = time.monotonic()
        if any(p.addr == addr for p in self.peers.values()):
            return
        if now - self.contacted.get(addr, -1e9) < CONTACT_AGAIN:
            return
        self.contacted[addr] = now
        self.send_json(addr, t="hello", name=self.name, v=PROTOCOL, re=0)

    def hello_in(self, m, addr):
        if m.get("v") != PROTOCOL:
            return
        nid = m["id"]
        p = self.peers.get(nid)
        new = p is None
        if new:
            p = self.peers[nid] = Peer(nid, addr)
        p.addr, p.name, p.last = addr, str(m.get("name", ""))[:16], time.monotonic()
        if new:
            self.log("node %s (%s) at %s:%d" % ((nid[:8], p.name) + addr))
            if self.search:
                self.send_json(p.addr, **self.search)
        if not m.get("re"):
            self.send_json(addr, t="hello", name=self.name, v=PROTOCOL, re=1)

    def on_ping(self, p, m):
        self.send_json(p.addr, t="pong")

    def on_pong(self, p, m):
        pass

    def lan_heard(self, data, addr):
        if data[:5] != MAGIC + bytes([V_JSON]):
            return
        try:
            m = json.loads(data[5:])
        except ValueError:
            return
        if isinstance(m, dict) and m.get("t") == "lan" and m.get("id") != self.id and isinstance(m.get("port"), int):
            self.contact((addr[0], m["port"]))

    # -- the network --------------------------------------------------------------------------------------------

    async def ticker(self):
        while True:
            await asyncio.sleep(0.5)
            try:
                self.tick()
            except Exception as e:   # the node goes on: one bad message must not stop the game's matchmaking
                self.log("tick: %r" % e)

    def tick(self):
        now = time.monotonic()
        playing = set(x["id"] for x in self.world["players"]) if self.world else set()
        for p in list(self.peers.values()):
            if now - p.last > PEER_TIMEOUT and p.id not in playing:
                self.log("node %s (%s) gone quiet" % (p.id[:8], p.name))
                del self.peers[p.id]
            elif now - p.pinged > PING_EVERY:
                p.pinged = now
                self.send_json(p.addr, t="ping")
        if self.use_lan and now - self.lan_sent > LAN_EVERY:
            self.lan_sent = now
            try:
                self.t.sendto(MAGIC + bytes([V_JSON]) + json.dumps({"t": "lan", "id": self.id, "port": self.port}).encode(),
                              (LAN_GROUP, LAN_PORT))
            except OSError:
                pass
        if self.search and now - self.search_sent > SEARCH_EVERY:
            self.search_sent = now
            self.to_all(**self.search)
        if self.proposal and now > self.proposal["until"]:
            for nid in self.proposal["members"]:
                if nid not in self.proposal["accepted"] and nid in self.peers:
                    self.peers[nid].busy_until = now + BUSY
            self.abort("no answer from every node")
        if self.lock and self.lock["leader"] != self.id and now > self.lock["until"]:
            self.lock = None
        self.match()

    async def dht_loop(self):
        while True:
            try:
                for addr in await self.dht.lookup(KEY, announce_port=self.port):
                    if addr != self.dht.public:
                        self.contact(addr)
            except Exception as e:
                self.log("dht: %r" % e)
            started = time.monotonic()
            while time.monotonic() - started < DHT_EVERY:
                await asyncio.sleep(1.0)
                if self.search and time.monotonic() - started >= DHT_SEARCHING_EVERY:
                    break

    # -- Quick Play -----------------------------------------------------------------------------------------------

    def start_search(self, s):
        self.local = s
        self.search = {"t": "search", "name": self.name, "build": "%016x" % s.build, "quick": s.quick, "mode": s.mode,
                       "minp": s.minp, "maxp": s.maxp, "count": s.count, "entries": [b64(e) for e in s.entries],
                       "p2p": self.p2p_port}
        self.search_since = time.monotonic()
        self.search_sent = 0.0
        self.last_update = None
        self.log("search: %s, mode %d, players %d..%d%s; %d nodes known" % (
            self.name, s.mode, s.minp, s.maxp, " (Quick Play)" if s.quick else "", len(self.peers)))

    def cancel_search(self, why):
        if self.search is None:
            return
        self.log("search over: %s" % why)
        self.to_all(t="cancel")
        if self.proposal:
            self.abort("our search is over")
        self.search = self.local = None
        self.lock = None

    def on_search(self, p, m):
        entries = m["entries"]
        ok = (isinstance(entries, list) and 0 < len(entries) <= MAX_PLAYERS and m["count"] == len(entries) and
              all(unb64(e, mp_sam.ENTRY_SEARCH) for e in entries) and isinstance(m["build"], str) and
              len(m["build"]) == 16 and isinstance(m["p2p"], int) and isinstance(m["mode"], int))
        if not ok:
            return
        if p.search is None:
            self.log("node %s (%s) searches: mode %d" % (p.id[:8], m.get("name"), m["mode"]))
        p.search, p.search_at = m, time.monotonic()

    def on_cancel(self, p, m):
        p.search = None

    def fits(self, m):
        mine = self.search
        return (m["build"] == mine["build"] and bool(m["quick"]) == bool(mine["quick"]) and
                (mine["quick"] or m["mode"] == mine["mode"]))

    def match(self):
        """The leader's part: the players searching with ours, the mode they take, and a proposal."""
        if not self.search or self.lock or self.proposal or self.local is None:
            return
        now = time.monotonic()
        cands = sorted((p for p in self.peers.values() if p.search and now - p.search_at < SEARCH_TIMEOUT and
                        now >= p.busy_until and self.fits(p.search)), key=lambda p: p.id)
        group, names = [(self.id, self.search)], {self.name.lower()}
        for p in cands:
            n = str(p.search.get("name", "")).lower()
            if n in names:          # one name once: the runtime finds players by it
                continue
            names.add(n)
            group.append((p.id, p.search))
        entries = [unb64(e) for _, m in group for e in m["entries"]]
        if self.last_update != len(entries):
            self.last_update = len(entries)
            self.mm.update(self.local, self.search["mode"], entries[:MAX_PLAYERS])
        if min(nid for nid, _ in group) != self.id or now < self.next_propose:
            return                  # another node leads, or ours waits a moment after a proposal that failed
        late = now - self.search_since >= self.mm.quick_wait
        for n in range(len(group), 1, -1):
            if sum(m["count"] for _, m in group[:n]) > MAX_PLAYERS:
                continue
            objs = [types.SimpleNamespace(count=m["count"], quick=bool(m["quick"]), mode=m["mode"], minp=m["minp"],
                                          maxp=m["maxp"]) for _, m in group[:n]]
            mode = self.mm.pick_mode(objs, late)
            if mode is not None:
                self.propose(group[:n], mode)
                return

    def propose(self, group, mode):
        wid = struct.unpack(">I", os.urandom(4))[0] or 1
        entries = [unb64(e) for _, m in group for e in m["entries"]]
        blob = mp_sam.world_blob_of(mode, entries)
        players = [{"id": nid, "name": m["name"], "p2p": m["p2p"]} for nid, m in group]
        now = time.monotonic()
        self.proposal = {"wid": wid, "members": [nid for nid, _ in group], "accepted": {self.id}, "mode": mode,
                         "blob": blob, "players": players, "until": now + PROPOSE_TIMEOUT}
        self.lock = {"wid": wid, "leader": self.id, "until": now + LOCK_TIMEOUT}
        self.log("proposing world %d, mode %d: %s" % (wid, mode, [x["name"] for x in players]))
        for nid in self.proposal["members"][1:]:
            self.send_json(self.peers[nid].addr, t="propose", wid=wid, mode=mode, blob=b64(blob), players=players)

    def on_propose(self, p, m):
        now = time.monotonic()
        players, blob = m["players"], unb64(m["blob"])
        ids = [x["id"] for x in players]
        mine = [unb64(e) for e in self.search["entries"]] if self.search else []
        rows = blob[0x11] if blob is not None and len(blob) >= 0x13 else -1
        ok = (self.search is not None and self.proposal is None and (self.lock is None or now > self.lock["until"])
              and self.id in ids and p.id == min(ids) and ids[0] == p.id and rows > 0
              and len(blob) == 0x13 + rows * mp_sam.ENTRY and
              all(any(blob[0x13 + i * mp_sam.ENTRY:0x13 + i * mp_sam.ENTRY + mp_sam.ENTRY_SEARCH] == e
                      for i in range(rows)) for e in mine))
        if ok:
            self.lock = {"wid": m["wid"], "leader": p.id, "until": now + LOCK_TIMEOUT, "players": players, "blob": blob}
        self.send_json(p.addr, t="accept" if ok else "reject", wid=m["wid"])

    def on_accept(self, p, m):
        pr = self.proposal
        if not pr or m["wid"] != pr["wid"] or p.id not in pr["members"]:
            return
        pr["accepted"].add(p.id)
        if len(pr["accepted"]) == len(pr["members"]):
            loop = asyncio.get_running_loop()
            for nid in pr["members"][1:]:      # three times: a node that misses it plays a world of its own
                for k in range(3):
                    loop.call_later(0.2 * k, lambda a=self.peers[nid].addr: self.send_json(a, t="commit", wid=pr["wid"]))
            self.proposal = None
            self.enter_world(pr["wid"], pr["blob"], pr["players"], pr["mode"])

    def on_reject(self, p, m):
        pr = self.proposal
        if pr and m["wid"] == pr["wid"]:
            p.busy_until = time.monotonic() + BUSY
            self.abort("%s said no" % (p.name or p.id[:8]))

    def abort(self, why):
        pr = self.proposal
        if not pr:
            return
        self.log("world %d dropped: %s" % (pr["wid"], why))
        for nid in pr["members"][1:]:
            if nid in self.peers:
                self.send_json(self.peers[nid].addr, t="abort", wid=pr["wid"])
        self.proposal = self.lock = None
        self.next_propose = time.monotonic() + 1.0 + random.random()

    def on_commit(self, p, m):
        lk = self.lock
        if lk and lk.get("blob") is not None and lk["wid"] == m["wid"] and lk["leader"] == p.id:
            self.enter_world(lk["wid"], lk["blob"], lk["players"], lk["blob"][0x10])

    def on_abort(self, p, m):
        if self.lock and self.lock["wid"] == m["wid"] and self.lock["leader"] == p.id:
            self.lock = None

    def enter_world(self, wid, blob, players, mode):
        q = self.local
        self.world = {"wid": wid, "players": players}
        for x in players:
            if x["id"] == self.id or x["id"] not in self.peers:
                continue
            name = str(x["name"])[:16]
            old = self.srv.players.get(name.lower())
            if old is not None and not getattr(old, "remote", False):
                continue            # our own game's name: never another player's
            self.srv.players[name.lower()] = RemotePlayer(self, self.peers[x["id"]], name, int(x["p2p"]))
        self.log("world %d, mode %d: %s" % (wid, mode, [x["name"] for x in players]))
        self.to_all(t="cancel")
        self.search = self.local = self.lock = None
        if q is not None:
            self.mm.deliver(q, wid, blob)

    # -- signaling and the relay through the nodes ----------------------------------------------------------------

    def sig_out(self, peer, to_name, kind, payload):
        self.send_json(peer.addr, t="sig", to=to_name, k=kind, p=b64(payload))

    def on_sig(self, p, m):
        to = self.srv.players.get(str(m["to"]).lower())
        payload = unb64(m["p"])
        kind = int(m["k"])
        if to is None or getattr(to, "remote", False) or payload is None or len(payload) < 16:
            return
        sender = self.srv.players.get(nss.name_of(payload[:16]).lower())
        if not isinstance(sender, RemotePlayer) or sender.peer is not p:
            return                  # only the node a player plays behind speaks for it
        if kind in (nss.ACTIVATED, nss.MOVED) and len(payload) >= 22:
            payload = payload[:16] + nss.ip4(p.addr[0]) + payload[20:22]   # where we see its node
        if kind == nss.ACTIVATED:
            sender.activated.add(to)
        elif kind == nss.DEACTIVATED:
            sender.activated.discard(to)
        elif kind == nss.GONE:
            sender.activated.clear()
            to.activated.discard(sender)
            self.srv.players.pop(sender.name.lower(), None)
        to.send(kind, payload)

    def relay_out(self, peer, from_name, to_name, payload):
        try:
            self.t.sendto(MAGIC + bytes([V_RELAY]) + nss.oid(from_name) + nss.oid(to_name) + payload, peer.addr)
        except OSError:
            pass

    def relay_in(self, data, addr):
        if len(data) < 32:
            return
        sender = self.srv.players.get(nss.name_of(data[:16]).lower())
        to = self.srv.players.get(nss.name_of(data[16:32]).lower())
        if (not isinstance(sender, RemotePlayer) or sender.peer.addr != addr or to is None or
                getattr(to, "remote", False) or to.udp is None or not nss.linked(sender, to)):
            return
        self.sig_udp.sendto(nss.UDP_MAGIC + bytes([nss.U_RELAYED]) + nss.oid(sender.name) + data[32:], to.udp)


class Running:
    """A node on an event loop of its own (a thread), for tests and scripts that go on meanwhile."""

    def __init__(self, node, **ports):
        import threading
        self.node = node
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()
        self.error = None

        def run():
            asyncio.set_event_loop(self.loop)
            try:
                self.ports = self.loop.run_until_complete(node.start(**ports))
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

    def call(self, fn, *args):
        """fn(*args) on the node's loop, and its result."""
        import concurrent.futures
        f = concurrent.futures.Future()

        def go():
            try:
                f.set_result(fn(*args))
            except Exception as e:
                f.set_exception(e)
        self.loop.call_soon_threadsafe(go)
        return f.result(5)

    def stop(self):
        async def shut():
            self.node.close()
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
