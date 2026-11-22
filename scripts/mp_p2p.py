"""Multiplayer with no host (docs/notes/2026-11-22-multiplayer-phase6.md, phase7.md): the node each player's game
runs when the launcher's Multiplayer is on Auto (scripts/mp_node.py auto), and the community node anyone can run.

On this PC the node is the game's matchmaker (SAM) and signaling server, as a host's node is (phase 5), but for its
own game only. With the other players' nodes it keeps a network of its own, on one UDP socket: it finds them through
the BitTorrent DHT (mp_dht.py: every node announces itself under one key and looks up the others), on this PC's
network by multicast, and at the nodes the settings name; then every node says hello to the ones it found and pings
them now and then.

Getting through routers (phase 7). A node asks its router to forward its port (UPnP, mp_upnp.py), and once the router
has (with the address outside the DHT sees), it gives the others that address and port itself (in hello, in what
nodes tell of it, on the DHT): a router may still send the node's own packets out from another port, which is no way
in. It says how it can be reached: open (a forwarded port, a community node), easy (the DHT saw it at one port: a router that maps by
source) or hard (one that maps by destination). Nodes tell each other which nodes they know; a node that hears of
one it does not know asks the node that knows it for an introduction, and both then say hello to each other's
addresses (the one the introducer sees and their own network's) for a few seconds: two easy routers let that
through. When nothing gets through, the two talk through the node that introduced them, which carries their
messages and their games' datagrams (a few pairs at most).

Quick Play: a node whose game searches tells every node it knows, again every two seconds. The node with the smallest
id among the players searching together leads: it picks the game mode as our matchmaker does (mp_sam.py), builds the
world (its own player first: the host) and proposes it; a node that is searching and not promised elsewhere accepts;
with every yes the leader commits, and every node gives its game the same world. A no or no answer ends the proposal
and the leader tries again without the node that said no.

Who is online: every node says what its player is doing (ready: the node runs, in the launcher or the game; lobby:
the game is in the multiplayer menu; searching: Quick Play; playing: a match), in its hello, its pings (and at once
when it changes) and in what other nodes tell of it; the node writes the players it knows of into a file the
launcher shows (status_file). A node that is asked to stop (stop_file appears) says goodbye first, so the others
take it off their lists at once instead of after a minute of silence.

Signaling: in a world, each other player is a RemotePlayer of the node's signaling server. Its messages
(ACTIVATED, DEACTIVATED, GONE, MOVED) go to the node it plays behind, which hands them to its game with the address
it sees our node at; datagrams the runtime relays (two games that cannot reach each other) go the same way.

Messages, on UDP: b"ASCR" and then
    1 JSON, with the sender's id
    2 from (16) to (16) and a game datagram the runtime relays
    3 to (8, a node id) and a message of kind 2 for the node that carries it on: from a node to the one between
    4 from (8) and that message: from the node between to the one it is for
"""
import argparse
import asyncio
import base64
import json
import os
import random
import socket
import struct
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "ps3recomp", "tools"))
import mp_dht  # noqa: E402
import mp_sam  # noqa: E402
import mp_upnp  # noqa: E402
import np_signaling_server as nss  # noqa: E402

MAGIC = b"ASCR"
V_JSON, V_RELAY, V_FWD, V_FWDED = 1, 2, 3, 4
PROTOCOL = 1
KEY = mp_dht.key("ascension-r/multiplayer/%d" % PROTOCOL)   # what every node announces on the DHT
NODE_PORT = 36102
LAN_GROUP, LAN_PORT = "239.255.65.82", 36103                 # the nodes on this PC's network
PING_EVERY, PEER_TIMEOUT = 15.0, 60.0
SEARCH_EVERY, SEARCH_TIMEOUT = 2.0, 7.0
PROPOSE_TIMEOUT, LOCK_TIMEOUT, BUSY = 2.5, 4.0, 5.0
LAN_EVERY, CONTACT_AGAIN = 5.0, 30.0
DHT_EVERY, DHT_SEARCHING_EVERY, POKE_EVERY = 300.0, 30.0, 5.0
GOSSIP_EVERY, GOSSIP_MAX = 20.0, 32
PUNCH_FOR, PUNCH_EVERY, INTRO_AGAIN = 4.0, 0.25, 60.0
INTRO_AGAIN_CARRIED = 600.0   # a node reached through another: a direct path tried again this seldom
RELAY_PAIRS = 8                    # the pairs of nodes one node carries for at a time
UPNP_LEASE, UPNP_RENEW = 3600, 1800
MAX_PLAYERS = 8
STATES = ("ready", "lobby", "searching", "playing")


def b64(b):
    return base64.b64encode(b).decode("ascii")


def unb64(s, n=None):
    try:
        b = base64.b64decode(s, validate=True)
    except (ValueError, TypeError):
        return None
    return b if n is None or len(b) == n else None


def addr_of(v):
    """An (ip, port) a message gave as [ip, port], or None."""
    try:
        ip, port = v
        socket.inet_aton(ip)
        port = int(port)
        return (ip, port) if 0 < port < 65536 and ip.count(".") == 3 else None
    except (TypeError, ValueError, OSError):
        return None


def local_addresses():
    """This PC's IPv4 addresses on its networks (not loopback or self-assigned)."""
    try:
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []
    return [ip for ip in ips if not ip.startswith(("127.", "169.254."))][:4]


class Peer:
    """Another player's node: reached at addr, or through the node via when nothing got through."""

    def __init__(self, nid, addr):
        self.id, self.addr = nid, addr
        self.via = None
        self.public = None          # its address as the node that told us of it sees it
        self.forwarded = None       # the address and port its router forwards to it (UPnP), as it said
        self.name = ""
        self.nat = "?"
        self.lan = []
        self.relays = False         # it carries other nodes' messages
        self.knows = {}             # the nodes it told us it knows: id -> what it said of them
        self.state = "ready"        # what its player is doing (STATES)
        self.last = self.pinged = self.gossiped = time.monotonic()
        self.search = None          # its game's search while it searches (the message)
        self.search_at = 0.0
        self.busy_until = 0.0       # said no to a world, or did not answer: not proposed to before then

    def ip(self):
        return (self.addr or self.public or ("0.0.0.0", 0))[0]


class RemotePlayer:
    """A player of the signaling server whose game is behind another node: its messages and the datagrams relayed to
    it go to that node, which hands them on."""
    remote = True

    def __init__(self, node, peer, name, port):
        self.node, self.peer = node, peer
        self.name, self.port = name, port
        self.ip = peer.ip()
        self.server_ip = "0.0.0.0"    # what a message to it says of our player's address: its node puts its own in
        self.local_ip = None
        self.udp = None
        self.token = 0
        self.activated = set()

    def send(self, kind, payload=b""):
        self.node.sig_out(self.peer, self.name, kind, payload)

    def where_for(self, viewer):
        return self.peer.ip(), self.port

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
        if conn.closed:
            self.node.set_playing(False)

    def session_opened(self, conn, service):
        if service == mp_sam.GAME_TRACKER:
            self.node.set_playing(True)
        self.node.presence()

    def session_closed(self, conn, service):
        if service == mp_sam.GAME_TRACKER:
            self.node.set_playing(False)

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
                 dht_cache=None, quick_wait=5.0, boot=None, private=False, nodes=(), relays=True, upnp=False,
                 community=False, direct=True, status_file=None, stop_file=None):
        self.id = os.urandom(8).hex()
        self.name, self.log, self.p2p_port = name, log, p2p_port
        self.want_port, self.use_lan, self.use_dht, self.use_upnp = node_port, lan, dht, upnp
        self.dht_cache, self.boot, self.private = dht_cache, boot, private
        self.nodes = list(nodes)        # (host, port): nodes the settings name (a community node)
        self.node_addrs = set()         # their addresses, once looked up
        self.direct = direct            # off (tests): no node but the named ones is reached itself
        self.status_file = status_file  # where the players this node knows of are written (the launcher reads it)
        self.stop_file = stop_file      # its appearing asks the node to stop
        self.stopped = False
        self.playing = False            # our game is in a match
        self.said_state = "ready"
        self.status_written = None
        self.relays = relays or community
        self.community = community      # no game here: it introduces nodes and carries their messages
        self.nat = "open" if community else "?"
        self.lan_addrs = []
        self.peers = {}
        self.contacted = {}             # address -> when we last said hello there
        self.punching = {}              # node id -> {addrs, until, next, via, name}
        self.intro_asked = {}           # node id -> when we last asked for it
        self.carrying = {}              # (id, id) -> when we last carried a message between the two
        self.dht_found, self.poked = [], 0.0
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
        self.gateway = self.gateway_ip = None
        self.forwarded = None           # (ip, port) our router forwards to this node (UPnP), once it is public
        self.mm = Matchmaker(self, quick_wait, log)
        self.srv = nss.Server(lambda text: log("[signaling] " + text))
        self.servers = []
        self.tasks = []
        self.ports = (0, 0, 0, 0)

    # -- start ------------------------------------------------------------------------------------------------------

    async def start(self, sam_port=10070, geo_port=10012, sig_port=nss.DEFAULT_PORT):
        """The game's matchmaker and signaling server on this PC (each port, or any when it is taken; none for a
        community node), the node's socket (NODE_PORT, or any), the LAN, the DHT and the router. The ports taken:
        (sam, geo, signaling, node)."""
        loop = asyncio.get_running_loop()

        async def server(handler, port):
            try:
                return await asyncio.start_server(handler, "127.0.0.1", port)
            except OSError:
                return await asyncio.start_server(handler, "127.0.0.1", 0)

        async def signaling(port):
            """The signaling server's TCP and UDP, on one number as the game has them: port, or another when it is
            taken, or when UDP cannot have it (Windows keeps ranges of ports by protocol, for Hyper-V and the like)."""
            for attempt in range(20):
                sig = await server(lambda r, w: nss.Player(self.srv, r, w).run(), port if attempt == 0 else 0)
                number = sig.sockets[0].getsockname()[1]
                try:
                    udp, _ = await loop.create_datagram_endpoint(lambda: nss.Udp(self.srv),
                                                                 local_addr=("127.0.0.1", number))
                    return sig, udp, number
                except OSError:
                    sig.close()
                    await sig.wait_closed()
            raise OSError("no port that both TCP and UDP can have for the signaling server")
        front = (0, 0, 0)
        if not self.community:
            sam = await server(lambda r, w: mp_sam.Client(self.mm, r, w).run(), sam_port)
            geo = await server(mp_sam.geo, geo_port)
            sig, self.sig_udp, sport = await signaling(sig_port)
            self.srv.udp_port = sport
            self.servers = [sam, geo, sig]
            front = (sam.sockets[0].getsockname()[1], geo.sockets[0].getsockname()[1], sport)
        try:
            await loop.create_datagram_endpoint(lambda: Socket(self), local_addr=("0.0.0.0", self.want_port))
        except OSError:
            if self.community:
                raise
            await loop.create_datagram_endpoint(lambda: Socket(self), local_addr=("0.0.0.0", 0))
        self.port = self.t.get_extra_info("sockname")[1]
        self.lan_addrs = [[ip, self.port] for ip in local_addresses()]
        if self.use_lan:
            await self.lan_start(loop)
        if self.use_dht:
            self.dht = mp_dht.Dht(lambda d, a: self.t.sendto(d, a), self.log, self.dht_cache,
                                  boot=self.boot or mp_dht.BOOTSTRAP, private=self.private)
            self.tasks.append(asyncio.ensure_future(self.dht_loop()))
        if self.use_upnp:
            self.tasks.append(asyncio.ensure_future(self.upnp_loop()))
        if self.nodes:
            self.tasks.append(asyncio.ensure_future(self.nodes_loop()))
        self.tasks.append(asyncio.ensure_future(self.ticker()))
        self.ports = front + (self.port,)
        self.log("%s %s%s: %snode port %d%s%s%s%s" % (
            "community node" if self.community else "node", self.id[:8], "" if self.community else " for " + self.name,
            "" if self.community else "matchmaker %d, geo %d, signaling %d on this PC; " % front, self.port,
            ", LAN" if self.use_lan else "", ", DHT" if self.use_dht else "", ", UPnP" if self.use_upnp else "",
            ", carries for others" if self.relays else ""))
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
            if not getattr(pl, "remote", False) and getattr(pl, "w", None) is not None:
                pl.w.close()
        for t in self.tasks:
            t.cancel()
        for t in (self.t, self.lan_t, self.sig_udp):
            if t:
                t.close()
        if self.dht:
            self.dht.save_cache()
        if self.gateway:   # the router's mapping goes now; a node that is killed leaves it to run out
            threading.Thread(target=self.unmap, args=(self.gateway, self.port), daemon=True).start()

    @staticmethod
    def unmap(gateway, port):
        try:
            gateway.delete(port)
        except mp_upnp.Error:
            pass

    # -- messages ---------------------------------------------------------------------------------------------------

    def send_json(self, addr, /, **m):
        m["id"] = self.id
        try:
            self.t.sendto(MAGIC + bytes([V_JSON]) + json.dumps(m, separators=(",", ":")).encode(), addr)
        except (OSError, AttributeError, TypeError):
            pass

    def send_to(self, p, /, **m):
        """A message to a node: to its address, or through the node between when it has none."""
        if p.via is not None:
            m["id"] = self.id
            self.send_json(p.via.addr, t="fwd", to=p.id, m=m)
        elif p.addr is not None:
            self.send_json(p.addr, **m)

    def to_all(self, **m):
        for p in list(self.peers.values()):
            self.send_to(p, **m)

    def hello(self, re):
        return {"t": "hello", "name": self.name, "v": PROTOCOL, "re": re, "nat": self.nat, "lan": self.lan_addrs,
                "relays": self.relays, "state": self.state(), "fwd": list(self.forwarded) if self.forwarded else None}

    def state(self):
        if self.community:
            return "ready"
        if self.playing:
            return "playing"
        if self.search:
            return "searching"
        return "lobby" if self.mm.clients else "ready"

    def set_playing(self, on):
        if self.playing != on:
            self.playing = on
            self.presence()

    def presence(self):
        """Our player's state to every node at once, when it changed."""
        st = self.state()
        if st != self.said_state:
            self.said_state = st
            self.to_all(t="ping", state=st)

    def players(self):
        """(name, state, how) of every player this node knows of: reached itself, through another node, or heard of
        from one."""
        out, seen = [], {self.id}
        for p in sorted(self.peers.values(), key=lambda p: p.name.lower()):
            seen.add(p.id)
            if p.name and p.name != "community":
                out.append((p.name, p.state, "through" if p.via is not None else "direct"))
        for p in list(self.peers.values()):
            for nid, e in p.knows.items():
                if nid not in seen and e.get("name") and e.get("name") != "community":
                    seen.add(nid)
                    st = e.get("state") if e.get("state") in STATES else "ready"
                    out.append((str(e["name"])[:16], st, "heard"))
        return out

    def write_status(self):
        if not self.status_file:
            return
        rows = self.players()
        clean = lambda s: "".join(c for c in str(s) if c.isprintable() and c not in "\t\r\n")
        text = "me\t%s\t%s\t%d\n" % (self.nat, self.state(), len(rows)) + "".join(
            "player\t%s\t%s\t%s\n" % (st, how, clean(name)) for name, st, how in rows)
        if text == self.status_written:
            return
        try:
            tmp = self.status_file + ".new"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, self.status_file)
            self.status_written = text
        except OSError:
            pass

    def peer_at(self, addr):
        for p in self.peers.values():
            if p.via is None and p.addr == addr:
                return p
        return None

    def received(self, data, addr):
        if data[:1] == b"d":
            if self.dht:
                self.dht.received(data, addr)
            return
        if len(data) < 5 or data[:4] != MAGIC:
            return
        kind = data[4]
        if kind == V_JSON:
            try:
                m = json.loads(data[5:])
            except ValueError:
                return
            if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"] != self.id:
                self.handle(m, addr)
        elif kind == V_RELAY:
            p = self.peer_at(addr)
            if p is not None:
                self.relay_in(data[5:], p)
        elif kind == V_FWD:
            self.carry_datagram(data[5:], addr)
        elif kind == V_FWDED:
            via = self.peer_at(addr)
            src = self.peers.get(data[5:13].hex()) if len(data) >= 13 else None
            if via is not None and src is not None and src.via is via and data[13:18] == MAGIC + bytes([V_RELAY]):
                src.last = time.monotonic()
                self.relay_in(data[18:], src)

    def handle(self, m, addr, via=None):
        """A message from the node m names: from addr, or carried by the node via."""
        t = m.get("t")
        if t == "hello":
            self.hello_in(m, addr, via)
            return
        p = self.peers.get(m["id"])
        if p is None:
            if via is None:
                self.contact(addr)                   # a node that knows us and we not it: hello (now and then)
            return
        p.last = time.monotonic()
        if via is None and p.via is None and p.addr != addr:   # its router gave it another port
            self.log("node %s now at %s:%d" % ((p.id[:8],) + addr))
            p.addr = addr
        handler = getattr(self, "on_" + str(t), None)
        if handler:
            try:
                handler(p, m)
            except (KeyError, TypeError, ValueError, AttributeError, IndexError) as e:
                self.log("node %s: %s message not understood (%r)" % (p.id[:8], t, e))

    def contact(self, addr):
        now = time.monotonic()
        if self.peer_at(addr) is not None or (not self.direct and addr not in self.node_addrs):
            return
        if now - self.contacted.get(addr, -1e9) < CONTACT_AGAIN:
            return
        self.contacted[addr] = now
        self.send_json(addr, **self.hello(0))

    def hello_in(self, m, addr, via=None):
        if m.get("v") != PROTOCOL or (via is None and not self.direct and addr not in self.node_addrs):
            return
        nid = m["id"]
        p = self.peers.get(nid)
        new = p is None
        if new:
            p = self.peers[nid] = Peer(nid, addr if via is None else None)
        if via is None:
            if p.via is not None:
                self.log("node %s (%s) reached at %s:%d itself" % ((nid[:8], p.name) + addr))
            p.via, p.addr = None, addr
            self.punching.pop(nid, None)
        elif p.via is None and p.addr is not None:
            pass                                    # it reaches us itself: that stays
        else:
            p.via, p.addr = via, None
        p.name, p.last = str(m.get("name", ""))[:16], time.monotonic()
        p.nat = m.get("nat") if m.get("nat") in ("open", "easy", "hard", "?") else "?"
        p.lan = [a for a in (addr_of(x) for x in (m.get("lan") or [])[:4]) if a]
        p.forwarded = addr_of(m.get("fwd")) if m.get("fwd") else None
        p.relays = bool(m.get("relays"))
        if m.get("state") in STATES:
            p.state = m["state"]
        if new:
            self.log("node %s (%s, %s) at %s" % (nid[:8], p.name, p.nat,
                                                 "%s:%d" % addr if via is None else "node %s" % via.id[:8]))
            if self.search:
                self.send_to(p, **self.search)
            p.gossiped = 0.0                        # tell it what we know at the next tick
        if not m.get("re"):
            self.send_to(p, **self.hello(1))

    def on_bye(self, p, m):
        self.drop(p, "left")

    def on_ping(self, p, m):
        if m.get("state") in STATES:
            p.state = m["state"]
        self.send_to(p, t="pong")

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

    # -- what nodes know of each other: introductions, punching, carrying ----------------------------------------

    def gossip(self, p):
        known = [{"id": q.id, "name": q.name, "nat": q.nat, "addr": list(q.addr), "lan": q.lan, "state": q.state,
                  "fwd": list(q.forwarded) if q.forwarded else None}
                 for q in self.peers.values() if q is not p and q.via is None and q.addr is not None]
        random.shuffle(known)
        self.send_to(p, t="peers", list=known[:GOSSIP_MAX])

    def on_peers(self, p, m):
        p.knows = {}
        for e in m["list"][:GOSSIP_MAX]:
            if not isinstance(e, dict) or not isinstance(e.get("id"), str) or len(e["id"]) != 16:
                continue
            a = addr_of(e.get("addr"))
            if a is None:
                continue
            p.knows[e["id"]] = e
            if e["id"] == self.id:
                continue
            q = self.peers.get(e["id"])
            if q is None or q.via is not None:
                if q is not None and q.public is None:
                    q.public = a
                self.meet(e, a, p, addr_of(e.get("fwd")) if e.get("fwd") else None)

    def meet(self, e, a, through, forwarded=None):
        """A node we know of but do not reach ourselves: hello to where it is (it may be open), and an introduction
        by the node that told us, once a minute at most (once in ten minutes for one we reach through another)."""
        now = time.monotonic()
        nid = e["id"]
        again = INTRO_AGAIN_CARRIED if nid in self.peers else INTRO_AGAIN
        if nid in self.punching or now - self.intro_asked.get(nid, -1e9) < again:
            return
        self.intro_asked[nid] = now
        if forwarded:
            self.contact(forwarded)                  # its router's open door first
        self.contact(a)
        if through.via is None:
            self.send_to(through, t="intro", to=nid)

    def on_intro(self, p, m):
        """Two nodes that know us and not each other: both say hello to the other's addresses now."""
        q = self.peers.get(m["to"])
        if q is None or q is p or q.via is not None or p.via is not None:
            return
        def where(n):
            return [list(a) for a in ([n.forwarded] if n.forwarded else []) + [n.addr] + n.lan]
        self.send_to(q, t="punch", peer=p.id, name=p.name, addrs=where(p))
        self.send_to(p, t="punch", peer=q.id, name=q.name, addrs=where(q))

    def on_punch(self, p, m):
        nid = m["peer"]
        q = self.peers.get(nid)
        if nid == self.id or (q is not None and q.via is None) or p.via is not None:
            return
        addrs = []
        for a in (addr_of(x) for x in m["addrs"][:6]):
            if a and a not in addrs:
                addrs.append(a)
        if not addrs:
            return
        self.punching[nid] = {"addrs": addrs, "until": time.monotonic() + PUNCH_FOR, "next": 0.0, "via": p,
                              "name": str(m.get("name", ""))[:16], "public": addrs[0]}
        self.log("punching toward node %s (%s) at %s" % (nid[:8], m.get("name"), ", ".join("%s:%d" % a for a in addrs)))

    def punch_tick(self, now):
        for nid, pu in list(self.punching.items()):
            q = self.peers.get(nid)
            if q is not None and q.via is None:
                del self.punching[nid]
                continue
            if now >= pu["until"]:
                del self.punching[nid]
                via = pu["via"]
                if self.peers.get(via.id) is via and via.via is None:
                    if q is None:
                        q = self.peers[nid] = Peer(nid, None)
                        q.name = pu["name"]
                    q.via, q.addr, q.public = via, None, pu["public"]
                    self.log("node %s (%s): nothing got through; through node %s" % (nid[:8], q.name, via.id[:8]))
                    self.send_to(q, **self.hello(0))
                continue
            if now >= pu["next"]:
                pu["next"] = now + PUNCH_EVERY
                for a in pu["addrs"]:
                    self.send_json(a, **self.hello(0))

    def carry(self, p, to):
        """Whether this node carries for the pair now (RELAY_PAIRS pairs at most)."""
        if not self.relays or to is None or to is p or to.via is not None or p.via is not None:
            return False
        pair = tuple(sorted((p.id, to.id)))
        now = time.monotonic()
        for k in [k for k, when in self.carrying.items() if now - when > PEER_TIMEOUT]:
            del self.carrying[k]
        if pair not in self.carrying and len(self.carrying) >= RELAY_PAIRS:
            return False
        if pair not in self.carrying:
            self.log("carrying for nodes %s and %s" % (p.id[:8], to.id[:8]))
        self.carrying[pair] = now
        return True

    def on_fwd(self, p, m):
        inner = m["m"]
        to = self.peers.get(m["to"])
        if isinstance(inner, dict) and inner.get("id") == p.id and self.carry(p, to):
            self.send_json(to.addr, t="fwded", src=p.id, m=inner)

    def on_fwded(self, p, m):
        inner = m["m"]
        if isinstance(inner, dict) and inner.get("id") == m["src"] and m["src"] != self.id:
            self.handle(inner, None, via=p)

    def carry_datagram(self, data, addr):
        p = self.peer_at(addr)
        if p is None or len(data) < 8:
            return
        to = self.peers.get(data[:8].hex())
        if self.carry(p, to):
            try:
                self.t.sendto(MAGIC + bytes([V_FWDED]) + bytes.fromhex(p.id) + data[8:], to.addr)
            except OSError:
                pass

    # -- the network --------------------------------------------------------------------------------------------

    async def ticker(self):
        while True:
            await asyncio.sleep(0.25)
            try:
                self.tick()
            except Exception as e:   # the node goes on: one bad message must not stop the game's matchmaking
                self.log("tick: %r" % e)

    def tick(self):
        if self.stop_file and not self.stopped and os.path.exists(self.stop_file):
            self.log("asked to stop: goodbye to %d nodes" % len(self.peers))
            self.to_all(t="bye")
            self.stopped = True
            return
        now = time.monotonic()
        playing = set(x["id"] for x in self.world["players"]) if self.world else set()
        for p in list(self.peers.values()):
            if now - p.last > PEER_TIMEOUT and p.id not in playing:
                self.drop(p, "gone quiet")
            elif now - p.pinged > PING_EVERY:
                p.pinged = now
                self.send_to(p, t="ping", state=self.state())
            if p.via is None and p.id in self.peers and now - p.gossiped > GOSSIP_EVERY:
                p.gossiped = now
                self.gossip(p)
        self.punch_tick(now)
        if self.use_lan and now - self.lan_sent > LAN_EVERY:
            self.lan_sent = now
            try:
                self.t.sendto(MAGIC + bytes([V_JSON]) + json.dumps({"t": "lan", "id": self.id, "port": self.port}).encode(),
                              (LAN_GROUP, LAN_PORT))
            except OSError:
                pass
        if self.search and self.dht_found and now - self.poked > POKE_EVERY:
            self.poked = now                        # two routers that map by source let crossed hellos through
            for a in self.dht_found[:20]:
                if self.peer_at(a) is None:
                    self.send_json(a, **self.hello(0))
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
        self.presence()
        self.write_status()

    def drop(self, p, why):
        if self.peers.get(p.id) is not p:
            return
        self.log("node %s (%s) %s" % (p.id[:8], p.name, why))
        del self.peers[p.id]
        for q in list(self.peers.values()):
            if q.via is p:
                self.drop(q, "lost with the node between")

    def classify(self):
        """How others can reach this node: open (a forwarded port, a community node), easy (one port for every
        node: punching gets through), hard (another port for each), ? (not known yet). The port the router forwards
        counts when the router's address outside is public and the one the DHT sees (or the DHT has not said yet):
        that address and port are then given out as they are (forwarded)."""
        nat = "?"
        public = self.dht.public[0] if self.dht and self.dht.public else None
        forwarded = None
        if self.gateway_ip and not mp_upnp.is_private(self.gateway_ip) and public in (None, self.gateway_ip):
            forwarded = (self.gateway_ip, self.port)
        if self.community or forwarded:
            nat = "open"
        elif self.dht and self.dht.symmetric:
            nat = "hard"
        elif public:
            nat = "easy"
        changed = nat != self.nat or forwarded != self.forwarded
        if nat != self.nat:
            self.log("reachable: %s" % nat)
        self.nat, self.forwarded = nat, forwarded
        if changed:
            self.to_all(**self.hello(1))

    async def dht_loop(self):
        while True:
            try:
                if self.forwarded:      # the port the router forwards, said outright: not the one it sends from
                    found = await self.dht.lookup(KEY, announce_port=self.forwarded[1], implied=False)
                else:
                    found = await self.dht.lookup(KEY, announce_port=None if self.nat == "hard" else self.port)
                self.classify()
                self.dht_found = [a for a in found if a not in (self.dht.public, self.forwarded) and
                                  self.peer_at(a) is None]
                for a in self.dht_found:
                    self.contact(a)
            except Exception as e:
                self.log("dht: %r" % e)
            started = time.monotonic()
            while time.monotonic() - started < DHT_EVERY:
                await asyncio.sleep(1.0)
                if self.search and time.monotonic() - started >= DHT_SEARCHING_EVERY:
                    break

    async def upnp_loop(self):
        loop = asyncio.get_running_loop()
        gw = await loop.run_in_executor(None, mp_upnp.discover)
        if gw is None:
            self.log("UPnP: no router answered")
            return
        while True:
            try:
                await loop.run_in_executor(None, lambda: gw.add(self.port, lease=UPNP_LEASE))
                ext = await loop.run_in_executor(None, gw.external_ip)
                if self.gateway is None:
                    self.log("UPnP: the router forwards UDP %d to this PC; its address outside is %s%s" % (
                        self.port, "private (another NAT in front)" if mp_upnp.is_private(ext) else "public",
                        "" if ext else " (it did not say)"))
                self.gateway, self.gateway_ip = gw, ext
                self.classify()
            except mp_upnp.Error as e:
                self.log("UPnP: %s" % e)
                if self.gateway is not None:    # renewed no more: the port is not given out on its word now
                    self.gateway = self.gateway_ip = None
                    self.classify()
                return
            await asyncio.sleep(UPNP_RENEW)

    async def nodes_loop(self):
        """The nodes the settings name: looked up and said hello to until they answer, and again whenever lost."""
        loop = asyncio.get_running_loop()
        while True:
            for host, port in self.nodes:
                try:
                    infos = await asyncio.wait_for(loop.getaddrinfo(host, port, family=socket.AF_INET,
                                                                    type=socket.SOCK_DGRAM), 5)
                    a = infos[0][4][:2]
                    self.node_addrs.add(a)
                    self.contact(a)
                except (OSError, asyncio.TimeoutError, IndexError):
                    self.log("node %s:%d not found" % (host, port))
            await asyncio.sleep(CONTACT_AGAIN)

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
            self.send_to(self.peers[nid], t="propose", wid=wid, mode=mode, blob=b64(blob), players=players)

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
        self.send_to(p, t="accept" if ok else "reject", wid=m["wid"])

    def on_accept(self, p, m):
        pr = self.proposal
        if not pr or m["wid"] != pr["wid"] or p.id not in pr["members"]:
            return
        pr["accepted"].add(p.id)
        if len(pr["accepted"]) == len(pr["members"]):
            loop = asyncio.get_running_loop()
            for nid in pr["members"][1:]:      # three times: a node that misses it plays a world of its own
                for k in range(3):
                    loop.call_later(0.2 * k, lambda q=self.peers[nid]: self.send_to(q, t="commit", wid=pr["wid"]))
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
                self.send_to(self.peers[nid], t="abort", wid=pr["wid"])
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
        self.playing = True             # until its GameTracker session ends, or the game goes
        if q is not None:
            self.mm.deliver(q, wid, blob)

    # -- signaling and the relay through the nodes ----------------------------------------------------------------

    def sig_out(self, peer, to_name, kind, payload):
        self.send_to(peer, t="sig", to=to_name, k=kind, p=b64(payload))

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
            payload = payload[:16] + nss.ip4(p.ip()) + payload[20:22]   # where we see its node
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
        packet = MAGIC + bytes([V_RELAY]) + nss.oid(from_name) + nss.oid(to_name) + payload
        try:
            if peer.via is not None:
                self.t.sendto(MAGIC + bytes([V_FWD]) + bytes.fromhex(peer.id) + packet, peer.via.addr)
            elif peer.addr is not None:
                self.t.sendto(packet, peer.addr)
        except OSError:
            pass

    def relay_in(self, data, peer):
        if len(data) < 32:
            return
        sender = self.srv.players.get(nss.name_of(data[:16]).lower())
        to = self.srv.players.get(nss.name_of(data[16:32]).lower())
        if (not isinstance(sender, RemotePlayer) or sender.peer is not peer or to is None or
                getattr(to, "remote", False) or to.udp is None or not nss.linked(sender, to)):
            return
        self.sig_udp.sendto(nss.UDP_MAGIC + bytes([nss.U_RELAYED]) + nss.oid(sender.name) + data[32:], to.udp)


class Running:
    """A node on an event loop of its own (a thread), for tests and scripts that go on meanwhile."""

    def __init__(self, node, **ports):
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


def main(argv):
    ap = argparse.ArgumentParser(description="A community node of Ascension-R's multiplayer: it introduces players' "
                                             "nodes to each other and carries for the ones that cannot reach each other.")
    ap.add_argument("role", choices=("community",))
    ap.add_argument("--port", type=int, default=NODE_PORT, help="the UDP port players' nodes reach it at (forward it)")
    ap.add_argument("--no-dht", action="store_true", help="not on the BitTorrent DHT: only nodes that name it find it")
    ap.add_argument("--lan", action="store_true", help="also found by multicast on this network")
    ap.add_argument("--upnp", action="store_true", help="ask the router to forward the port")
    ap.add_argument("--dht-cache", help="where the DHT nodes that answered are kept")
    ap.add_argument("--log", help="also write the log here")
    a = ap.parse_args(argv)
    out = open(a.log, "a", encoding="utf-8") if a.log else None

    def log(text):
        line = time.strftime("%H:%M:%S ") + text
        print(line, flush=True)
        if out:
            out.write(line + "\n")
            out.flush()

    async def run():
        node = Node("community", log, node_port=a.port, lan=a.lan, dht=not a.no_dht, dht_cache=a.dht_cache,
                    upnp=a.upnp, community=True)
        await node.start()
        log("players reach it with [online] nodes = <this machine>:%d" % node.port)
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            node.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
