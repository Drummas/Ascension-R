"""A small client of the BitTorrent DHT (BEP 5) for the multiplayer's node (scripts/mp_p2p.py;
docs/notes/2026-11-22-multiplayer-phase6.md): every node announces itself under one key and looks up the others
that did, as torrent clients find a torrent's peers without a tracker. It only asks (read-only, BEP 43): nobody
puts it in a routing table and it answers no one.

It shares the node's UDP socket: the node hands it what starts with "d" (a bencoded dictionary) and gives it a send
function. That socket's address as the DHT sees it is what the node announces (implied_port), the same one its own
messages come from.
"""
import asyncio
import hashlib
import ipaddress
import json
import os
import socket
import struct
import time

# Who answers a first question: the clients' usual bootstrap nodes. A node met once is kept (cache_file) and asked
# first next time, so a bootstrap name that does not resolve here stops nothing.
BOOTSTRAP = (("dht.libtorrent.org", 25401), ("dht.transmissionbt.com", 6881), ("router.bittorrent.com", 6881),
             ("router.utorrent.com", 6881))
K = 8              # the closest nodes a lookup ends on, and announces to
ALPHA = 4          # questions in flight at once
TIMEOUT = 2.0      # seconds a node has to answer
CACHE_MAX = 200


def key(text):
    """The info-hash every node of one program and version announces: SHA-1 of a name of its own."""
    return hashlib.sha1(text.encode()).digest()


# -- bencode ---------------------------------------------------------------------------------------------------

def bencode(o):
    if isinstance(o, bool):
        o = int(o)
    if isinstance(o, int):
        return b"i%de" % o
    if isinstance(o, str):
        o = o.encode()
    if isinstance(o, (bytes, bytearray)):
        return b"%d:%s" % (len(o), bytes(o))
    if isinstance(o, (list, tuple)):
        return b"l" + b"".join(bencode(x) for x in o) + b"e"
    if isinstance(o, dict):
        items = sorted((k.encode() if isinstance(k, str) else k, v) for k, v in o.items())
        return b"d" + b"".join(bencode(k) + bencode(v) for k, v in items) + b"e"
    raise TypeError("cannot bencode %r" % type(o))


def bdecode(data):
    """The value data holds, keys and strings as bytes; ValueError for anything that is not exactly one."""
    def at(i, depth):
        if depth > 32 or i >= len(data):
            raise ValueError("truncated")
        c = data[i:i + 1]
        if c == b"i":
            e = data.index(b"e", i)
            return int(data[i + 1:e]), e + 1
        if c == b"l":
            out, i = [], i + 1
            while data[i:i + 1] != b"e":
                v, i = at(i, depth + 1)
                out.append(v)
            return out, i + 1
        if c == b"d":
            out, i = {}, i + 1
            while data[i:i + 1] != b"e":
                k, i = at(i, depth + 1)
                if not isinstance(k, bytes):
                    raise ValueError("a key that is not a string")
                v, i = at(i, depth + 1)
                out[k] = v
            return out, i + 1
        if c.isdigit():
            colon = data.index(b":", i)
            n = int(data[i:colon])
            if n < 0 or colon + 1 + n > len(data):
                raise ValueError("a string past the end")
            return data[colon + 1:colon + 1 + n], colon + 1 + n
        raise ValueError("unknown type %r" % c)

    try:
        v, end = at(0, 0)
    except (IndexError, ValueError) as e:
        raise ValueError(str(e)) from None
    if end != len(data):
        raise ValueError("bytes after the value")
    return v


# -- compact addresses -------------------------------------------------------------------------------------------

def compact(ip, port):
    return socket.inet_aton(ip) + struct.pack(">H", port)


def uncompact(b):
    return socket.inet_ntoa(b[:4]), struct.unpack(">H", b[4:6])[0]


def nodes_of(blob):
    """(id, ip, port) of each 26-byte entry of a "nodes" string."""
    if not isinstance(blob, bytes):
        return []
    return [(blob[i:i + 20],) + uncompact(blob[i + 20:i + 26]) for i in range(0, len(blob) - 25, 26)]


def reachable(ip, port, private=False):
    """Worth asking: a public IPv4 address and a port (any address with private, for tests on one PC). A node that
    hands out a private address is wrong about it."""
    try:
        a = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return 0 < port < 65536 and (private or a.is_global)


def distance(a, b):
    return int.from_bytes(a, "big") ^ int.from_bytes(b, "big")


# -- the client --------------------------------------------------------------------------------------------------

class Dht:
    def __init__(self, send, log=lambda text: None, cache_file=None, node_id=None, boot=BOOTSTRAP, private=False):
        self.send = send                # send(data, (ip, port)): the node's socket
        self.log = log
        self.id = node_id or os.urandom(20)
        self.cache_file = cache_file
        self.boot = boot                # (host, port) of the nodes a first lookup asks
        self.private = private          # private addresses are nodes too (tests)
        self.pending = {}               # transaction id -> future
        self.good = {}                  # (ip, port) -> when it last answered
        self.public = None              # (ip, port): this socket as the DHT sees it (BEP 42's "ip"), the last answer
        self.symmetric = False          # nodes saw it at more than one port: a NAT that maps by destination
        self.queries = 0

    # What the node passes on: answers to our questions (we ask, we answer nothing).
    def received(self, data, addr):
        try:
            m = bdecode(data)
        except ValueError:
            return False
        if not isinstance(m, dict) or m.get(b"y") not in (b"r", b"e"):
            return isinstance(m, dict)
        f = self.pending.pop(m.get(b"t"), None)
        if f is None or f.done():
            return True
        ip = m.get(b"ip")
        if isinstance(ip, bytes) and len(ip) == 6:
            seen = uncompact(ip)
            if self.public is None or seen[0] != self.public[0]:
                self.log("dht: this node is %s:%d from outside" % seen)
            elif seen[1] != self.public[1] and not self.symmetric:
                # The same socket, another port for another node: a router that maps by destination. Peers then
                # cannot reach this node at the port the DHT holds; it reaches them, or a relay does.
                self.symmetric = True
                self.log("dht: the router here gives this socket another port for each node it talks to (a NAT "
                         "that maps by destination)")
            self.public = seen
        if m.get(b"y") == b"r" and isinstance(m.get(b"r"), dict):
            self.good[addr] = time.monotonic()
            f.set_result(m[b"r"])
        else:
            f.set_result(None)
        return True

    async def query(self, addr, q, args, timeout=TIMEOUT):
        t = os.urandom(2)
        while t in self.pending:
            t = os.urandom(2)
        f = asyncio.get_running_loop().create_future()
        self.pending[t] = f
        a = dict(args, id=self.id)
        self.queries += 1
        try:
            self.send(bencode({"t": t, "y": "q", "q": q, "a": a, "ro": 1}), addr)
            return await asyncio.wait_for(f, timeout)
        except (asyncio.TimeoutError, OSError):
            return None
        finally:
            self.pending.pop(t, None)

    async def bootstrap(self):
        """Where a lookup starts: the nodes kept from earlier, then the bootstrap names resolved."""
        out = []
        for ip, port in self.load_cache():
            if (ip, port) not in out:
                out.append((ip, port))
        loop = asyncio.get_running_loop()

        async def resolve(host, port):
            try:
                infos = await asyncio.wait_for(loop.getaddrinfo(host, port, family=socket.AF_INET,
                                                                type=socket.SOCK_DGRAM), 5)
                return [(i[4][0], port) for i in infos]
            except (OSError, asyncio.TimeoutError):
                return []
        for found in await asyncio.gather(*(resolve(h, p) for h, p in self.boot)):
            for addr in found[:1]:
                if addr not in out:
                    out.append(addr)
        return out

    async def lookup(self, info_hash, announce_port=None, max_queries=160, time_limit=25.0):
        """The peers announced under info_hash (a set of (ip, port)), by asking ever closer nodes (get_peers); with
        announce_port, this node is then announced to the closest ones that answered (announce_peer, implied_port:
        the port its questions come from)."""
        start = time.monotonic()
        nodes = {a: None for a in await self.bootstrap()}     # address -> its id, None until it says
        asked, answered, peers = set(), {}, set()
        while time.monotonic() - start < time_limit and len(asked) < max_queries:
            def far(a):
                return distance(nodes[a], info_hash) if nodes[a] else 1 << 161
            todo = sorted((a for a in nodes if a not in asked), key=far)
            best = sorted(answered, key=lambda a: distance(answered[a][0], info_hash))[:K]
            if not todo or (len(best) >= K and far(todo[0]) >= distance(answered[best[-1]][0], info_hash)):
                break
            batch = todo[:ALPHA]
            asked.update(batch)
            got = await asyncio.gather(*(self.query(a, "get_peers", {"info_hash": info_hash}) for a in batch))
            for a, r in zip(batch, got):
                if not r:
                    continue
                nid = r.get(b"id")
                if isinstance(nid, bytes) and len(nid) == 20:
                    answered[a] = (nid, r.get(b"token"))
                for v in r.get(b"values") or []:
                    if isinstance(v, bytes) and len(v) == 6:
                        peers.add(uncompact(v))
                for nid2, ip, port in nodes_of(r.get(b"nodes")):
                    if (ip, port) not in nodes and reachable(ip, port, self.private):
                        nodes[(ip, port)] = nid2
        if announce_port is not None:
            to = sorted((a for a in answered if isinstance(answered[a][1], bytes)),
                        key=lambda a: distance(answered[a][0], info_hash))[:K]
            got = await asyncio.gather(*(self.query(a, "announce_peer", {"info_hash": info_hash, "port": announce_port,
                                                                        "token": answered[a][1], "implied_port": 1})
                                         for a in to))
            self.log("dht: announced to %d of %d nodes" % (sum(1 for r in got if r is not None), len(to)))
        self.log("dht: %d nodes asked, %d answered, %d peers under the key, %.1f s" % (
            len(asked), len(answered), len(peers), time.monotonic() - start))
        self.save_cache()
        return peers

    def load_cache(self):
        if not self.cache_file:
            return []
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                return [(ip, int(port)) for ip, port in json.load(f)
                        if reachable(ip, int(port), self.private)][:CACHE_MAX]
        except (OSError, ValueError, TypeError):
            return []

    def save_cache(self):
        if not self.cache_file or not self.good:
            return
        newest = sorted(self.good, key=lambda a: -self.good[a])[:CACHE_MAX]
        try:
            tmp = self.cache_file + ".new"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([[ip, port] for ip, port in newest], f)
            os.replace(tmp, self.cache_file)
        except OSError:
            pass
