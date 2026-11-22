"""The servers God of War: Ascension's multiplayer plays through (docs/notes/2026-11-22-multiplayer-phase4.md): our
matchmaker (scripts/mp_sam.py) and the runtime's signaling server (ps3recomp/tools/np_signaling_server.py), for
players on other machines, who start the game with scripts/mp_play.py --server <this machine>.

    mp_server.py [--host 0.0.0.0] [--public-ip A.B.C.D] [--mode N] [--players N] [--no-relay] [--sam-port 10070]
                 [--geo-port 10012] [--signaling-port 36101] [--log-dir build/online]

What players must reach here: TCP 10070 (matchmaker), TCP 10012 (geo), TCP and UDP 36101 (signaling and relay).
Behind a router, forward those to this machine and give --public-ip, the address players elsewhere use. Players
reach each other directly on their P2P port (UDP 3658) when their routers let them, and through the relay here when
not. Two players meet in a two-player mode; a group of more waits for all of them with --players N (four: a mode for
four; three: give --mode too, as no mode is known to take three).
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ps3recomp", "tools"))
import mp_sam  # noqa: E402
import np_signaling_server  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(description="God of War: Ascension's multiplayer servers (matchmaker, signaling).")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--public-ip", help="the address players elsewhere reach this machine at, behind a router")
    ap.add_argument("--mode", type=int, help="the game mode of every Quick Play match")
    ap.add_argument("--players", type=int, help="Quick Play waits for this many players: one world for all")
    ap.add_argument("--no-relay", action="store_true", help="players who cannot reach each other do not play")
    ap.add_argument("--sam-port", type=int, default=10070)
    ap.add_argument("--geo-port", type=int, default=10012)
    ap.add_argument("--signaling-port", type=int, default=np_signaling_server.DEFAULT_PORT)
    ap.add_argument("--log-dir", default=os.path.join(ROOT, "build", "online"))
    a = ap.parse_args(argv)
    os.makedirs(a.log_dir, exist_ok=True)
    out = open(os.path.join(a.log_dir, "server.log"), "a", encoding="utf-8")

    def log(prefix):
        def write(text):
            line = time.strftime("%H:%M:%S ") + prefix + text
            out.write(line + "\n")
            out.flush()
            if not text.startswith(("<-", "  ->")):
                print(line, flush=True)
        return write

    sam = mp_sam.start(a.host, a.sam_port, a.geo_port, a.mode, log=log("[sam] "), players=a.players)
    sig = np_signaling_server.start(a.host, a.signaling_port, log("[signaling] "), a.public_ip, not a.no_relay)
    print("matchmaker on %s:%d, geo %d, signaling %d (TCP and UDP)%s" % (a.host, sam.ports[0], sam.ports[1],
                                                                        sig.port, "" if not a.no_relay else
                                                                        ", no relay"), flush=True)
    print("players: py scripts\\mp_play.py --server %s --name <their online id>" % (a.public_ip or "<this machine>"),
          flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sam.stop()
        sig.stop()
        out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
