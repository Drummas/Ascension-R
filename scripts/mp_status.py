#!/usr/bin/env python3
"""How many Ascension-R players are online on Auto, for the website (docs/notes/2026-11-23-online-status.md).

The nodes announced on the BitTorrent DHT under the multiplayer's key, looked up the way a player's node looks them up
(scripts/mp_p2p.py), and nothing more: this announces nothing and contacts no player. What it writes is the count
alone, with the time it was taken: no address and no name.

It is a rough count. A node behind a router that maps by destination does not announce itself, so it is not seen; a
node announces itself every 5 minutes and the DHT keeps an announce for up to about 30 after that, so one that has just
gone can still be counted; and Host and Join games never go on the DHT. players counts addresses (two players behind
one router count once), announced their address and port pairs.

usage: python scripts/mp_status.py [--out status.json] [--time-limit 25]
"""
import argparse
import asyncio
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_dht  # noqa: E402

# The key every node announces itself under: mp_p2p.py's KEY, protocol 1 (tests/test_mp_status.py keeps them the same,
# so this file needs nothing but mp_dht.py).
KEY = mp_dht.key("ascension-r/multiplayer/1")
FORMAT = 1      # of the JSON this writes


class _Socket(asyncio.DatagramProtocol):
    """The lookup's UDP socket: the DHT's answers go to it."""

    def __init__(self):
        self.dht = None

    def datagram_received(self, data, addr):
        if self.dht:
            self.dht.received(data, addr[:2])


async def check(boot=mp_dht.BOOTSTRAP, private=False, time_limit=25.0, log=lambda text: None, now=None):
    """The status: ok when some DHT node answered, players (addresses) and announced (address and port pairs) then,
    None otherwise; checked, the time in UTC; dht_nodes, how many DHT nodes answered."""
    loop = asyncio.get_running_loop()
    t, sock = await loop.create_datagram_endpoint(_Socket, local_addr=("0.0.0.0" if not private else "127.0.0.1", 0))
    try:
        sock.dht = mp_dht.Dht(lambda data, addr: t.sendto(data, addr), log, boot=boot, private=private)
        peers = await sock.dht.lookup(KEY, time_limit=time_limit)
        answered = len(sock.dht.good)
    finally:
        t.close()
    when = (now or datetime.datetime.now(datetime.timezone.utc)).replace(microsecond=0)
    ok = answered > 0
    return {"format": FORMAT, "checked": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": ok,
            "players": len({ip for ip, _ in peers}) if ok else None, "announced": len(peers) if ok else None,
            "dht_nodes": answered}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Count the Ascension-R players announced on the DHT (Auto).")
    ap.add_argument("--out", help="the JSON file to write (else printed)")
    ap.add_argument("--time-limit", type=float, default=25.0, help="seconds the lookup may take")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="the lookup's own lines too (they name this machine's address: not in a public log)")
    a = ap.parse_args(argv)
    log = (lambda text: print(text, file=sys.stderr)) if a.verbose else (lambda text: None)
    status = asyncio.run(check(time_limit=a.time_limit, log=log))
    text = json.dumps(status, indent=1) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(text, end="")
    return 0    # ok false is an answer too: the workflow then leaves the last count as it is


if __name__ == "__main__":
    sys.exit(main())
