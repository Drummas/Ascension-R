"""Multiplayer on this PC alone, as far as it goes (docs/notes/2026-11-22-multiplayer-phase1.md): builds our TSS,
starts the game signed in with a ticket of our own, every name it looks up pointed at 127.0.0.1 and nothing let
past this PC, and listens where our MatchConfig sends it (SAM 10070, geo 10012), writing down what arrives.

    mp_local.py [--exe build/Ascension-R.exe] [--out build/online] [--name <online id>] [-- <game arguments>]

On the title screen, right picks Multi-Player. A first profile starts the multiplayer tutorial; finished (or with a
profile that says so in TUS slot 1), the lobby's Quick Play connects to the matchmaker here, which only records the
connection: there is no matchmaker yet (phase 2). The game's own log is on (GOWA_GAME_LOG=1); the listeners write
<out>/listen.txt.
"""
import argparse
import os
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_tss  # noqa: E402

PORTS = {10070: "SAM", 10012: "geo"}


def listen(port, what, log, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(4)
    srv.settimeout(0.5)
    while not stop.is_set():
        try:
            c, peer = srv.accept()
        except socket.timeout:
            continue
        c.settimeout(3)
        data = b""
        try:
            while len(data) < 65536:
                b = c.recv(65536)
                if not b:
                    break
                data += b
        except socket.timeout:
            pass
        with log[1]:
            log[0].write("%s %s from %s:%d, %d bytes\n%s\n" % (time.strftime("%H:%M:%S"), what, peer[0], peer[1],
                                                                len(data), data.hex(" ", 16)))
            log[0].flush()
        print("[mp_local] %s: %d bytes" % (what, len(data)), flush=True)
        c.close()
    srv.close()


def main(argv):
    rest = []
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    ap = argparse.ArgumentParser(description="God of War: Ascension's multiplayer against stand-ins on this PC.")
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "Ascension-R.exe"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "online"))
    ap.add_argument("--name", default="", help="the online id (else the launcher's or the OS login)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    tss = os.path.join(a.out, "tss.bin")
    mp_tss.main(["build", os.path.join(ROOT, "online", "tss"), tss])
    env = dict(os.environ, PS3_NET_ONLINE="1", PSNR_SERVER="127.0.0.1:36100", PS3_NP_TEST_TICKET="1",
               PS3_NP_TSS_FILE=tss, PS3_NP_TUS_DIR=os.path.join(a.out, "np_tus"),
               PS3_NET_HOSTS="*=127.0.0.1", PS3_NET_LOOPBACK_ONLY="1", GOWA_GAME_LOG="1")
    if a.name:
        env["PS3_NP_ONLINE_ID"] = a.name
    stop = threading.Event()
    log = (open(os.path.join(a.out, "listen.txt"), "a", encoding="utf-8"), threading.Lock())
    for port, what in PORTS.items():
        threading.Thread(target=listen, args=(port, what, log, stop), daemon=True).start()
    print("[mp_local] TSS %s, TUS %s, listening on %s" % (tss, env["PS3_NP_TUS_DIR"],
                                                        ", ".join("%s %d" % (w, p) for p, w in PORTS.items())), flush=True)
    try:
        rc = subprocess.call([a.exe] + rest, cwd=os.path.dirname(a.exe), env=env)
    finally:
        stop.set()
        time.sleep(0.6)
        log[0].close()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
