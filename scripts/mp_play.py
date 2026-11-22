"""Play God of War: Ascension's multiplayer through a server of ours on another machine (docs/notes/
2026-11-22-multiplayer-phase4.md): the matchmaker and signaling server that scripts/mp_server.py runs.

    mp_play.py --server <host> [--name <online id>] [--p2p-port 3658] [--relay] [--sam-port 10070]
               [--signaling-port 36101] [--exe build/Ascension-R.exe] [--out build/online] [-- <game arguments>]

Builds our TSS with that server as the game's matchmaker, signs the game in with a ticket of our own, and points
every name the game looks up at the server; nothing else is reachable but this PC, the server, and the players the
signaling server introduces (PS3_NET_LOOPBACK_ONLY with PS3_NET_ALLOW). Every player needs an online id of their own
(--name, else the launcher's or the OS login). Peers reach each other directly when they can, through the server's
relay when they cannot; --relay always uses the relay.
"""
import argparse
import ipaddress
import os
import socket
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_tss  # noqa: E402

SIGNALING_PORT = 36101
SAM_PORT = 10070


def server_address(host):
    """The server's IPv4 address (a name is looked up here, once, as any program would)."""
    try:
        return str(ipaddress.IPv4Address(host))
    except ValueError:
        return socket.gethostbyname(host)


def build_tss(out_dir, server_ip, sam_port=SAM_PORT):
    os.makedirs(out_dir, exist_ok=True)
    name = "tss.bin" if server_ip == "127.0.0.1" and sam_port == SAM_PORT else "tss-%s-%d.bin" % (server_ip, sam_port)
    tss = os.path.join(out_dir, name)
    args = ["build", os.path.join(ROOT, "online", "tss"), tss]
    if server_ip != "127.0.0.1" or sam_port != SAM_PORT:
        args += ["--server", server_ip, "--sam-port", str(sam_port)]
    mp_tss.main(args)
    return tss


def game_env(base, server_ip, tss, tus, name=None, p2p_port=None, signaling_port=SIGNALING_PORT, relay=False,
             game_log=True):
    """The environment a game needs to play through server_ip, and nothing past it."""
    env = dict(base, PS3_NET_ONLINE="1", PSNR_SERVER="127.0.0.1:36100", PS3_NP_TEST_TICKET="1",
               PS3_NP_TSS_FILE=tss, PS3_NP_TUS_DIR=tus, PS3_NET_HOSTS="*=" + server_ip, PS3_NET_LOOPBACK_ONLY="1",
               PS3_NP_SIGNALING_SERVER="%s:%d" % (server_ip, signaling_port))
    for k in ("PS3_NET_ALLOW", "PS3_NP_SIGNALING_RELAY", "PS3_NP_ONLINE_ID", "PS3_NET_P2P_PORT", "GOWA_GAME_LOG"):
        env.pop(k, None)
    if not ipaddress.IPv4Address(server_ip).is_loopback:
        env["PS3_NET_ALLOW"] = server_ip
    if name:
        env["PS3_NP_ONLINE_ID"] = name
    if p2p_port:
        env["PS3_NET_P2P_PORT"] = str(p2p_port)
    if relay:
        env["PS3_NP_SIGNALING_RELAY"] = "1"
    if game_log:
        env["GOWA_GAME_LOG"] = "1"
    return env


def main(argv):
    rest = []
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    ap = argparse.ArgumentParser(description="God of War: Ascension's multiplayer through a server of ours.")
    ap.add_argument("--server", required=True, help="the machine running scripts/mp_server.py")
    ap.add_argument("--name", default="", help="your online id (else the launcher's or the OS login)")
    ap.add_argument("--p2p-port", type=int, help="the UDP port peers reach you at (3658)")
    ap.add_argument("--relay", action="store_true", help="always through the server's relay")
    ap.add_argument("--sam-port", type=int, default=SAM_PORT)
    ap.add_argument("--signaling-port", type=int, default=SIGNALING_PORT)
    ap.add_argument("--game-log", action="store_true", help="the game's own log on the console")
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "Ascension-R.exe"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "online"))
    a = ap.parse_args(argv)
    server_ip = server_address(a.server)
    tss = build_tss(a.out, server_ip, a.sam_port)
    env = game_env(os.environ, server_ip, tss, os.path.join(a.out, "np_tus"), a.name, a.p2p_port,
                   a.signaling_port, a.relay, a.game_log)
    print("[mp_play] server %s (matchmaker %d, signaling %d)%s" % (server_ip, a.sam_port, a.signaling_port,
                                                                  ", relay always" if a.relay else ""), flush=True)
    return subprocess.call([a.exe] + rest, cwd=os.path.dirname(a.exe), env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
