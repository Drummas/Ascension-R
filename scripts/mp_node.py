"""The multiplayer side of a player's game: what the game starts (port/multiplayer.cpp) with the Kit's Python when
the launcher's Multiplayer is on ([online] in the settings; docs/notes/2026-11-22-multiplayer-phase5.md, phase6.md).

    mp_node.py auto --name <online id> --elf <GOWA.elf> --dir <folder> [--relay] [--p2p-port N]
    mp_node.py join --server <host> --name <online id> --elf <GOWA.elf> --dir <folder> [--relay] [--p2p-port N]
    mp_node.py host --name <online id> --elf <GOWA.elf> --dir <folder> [--relay] [--p2p-port N] [--mode N]
                    [--players N]

Each builds our TSS from the player's own GOWA.elf with the matchmaker the game is to use (auto and host: this PC's;
join: the host's) and writes the game's environment into <dir>/game.env, one NAME=value a line (an empty value:
none), which the game applies before anything reads it. join then ends; host runs the matchmaker and the signaling
server on every address, for this PC's game and for the players who join it; auto runs the node of multiplayer with
no host (mp_p2p.py), which finds the other players' nodes itself. Both run until the game ends (the node is in the
game's job). Anything that stops it writes the reason into <dir>/node.error and ends with 2; what it does goes into
<dir>/node.log.
"""
import argparse
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # the tree, or the Kit's folder: the same layout under it
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "ps3recomp", "tools"))
import mp_play  # noqa: E402
import mp_tss  # noqa: E402

SAM_PORT, GEO_PORT = 10070, 10012
SIGNALING_PORT = mp_play.SIGNALING_PORT
TSS_BLOCKS = os.path.join(ROOT, "online", "tss")
ENV_FILE, ERROR_FILE, LOG_FILE = "game.env", "node.error", "node.log"
P2P = {}      # more for mp_p2p.Node (tests: no LAN, no DHT)
# Every variable the node decides: one it leaves out of a run is cleared, so nothing of another run or of the
# player's own environment says otherwise.
MANAGED = ("PS3_NET_ONLINE", "PSNR_SERVER", "PS3_NP_TEST_TICKET", "PS3_NP_TSS_FILE", "PS3_NP_TUS_DIR", "PS3_NET_HOSTS",
           "PS3_NET_LOOPBACK_ONLY", "PS3_NP_SIGNALING_SERVER", "PS3_NET_ALLOW", "PS3_NP_SIGNALING_RELAY",
           "PS3_NP_ONLINE_ID", "PS3_NET_P2P_PORT")


class Stop(Exception):
    """What the player is told: the game shows it."""


def clean_online_id(name):
    """The runtime's rule (np_psnr.c): 3-16 letters, digits, - and _, starting with a letter. The name as it is, or
    None: a name the runtime would change is not taken."""
    ok = 3 <= len(name or "") <= 16 and name[0].isascii() and name[0].isalpha() and \
        all(c.isascii() and (c.isalnum() or c in "-_") for c in name)
    return name if ok else None


def build_tss(elf, out, server_ip, sam_port=SAM_PORT, geo_port=GEO_PORT):
    """Our TSS with server_ip (and those ports) as the matchmaker and geo service, keyed from the player's GOWA.elf."""
    try:
        bf, iv = mp_tss.cipher(mp_tss.Elf(elf))
        blocks = mp_tss.read_folder(TSS_BLOCKS)
    except SystemExit as e:            # mp_tss says what is wrong and exits
        raise Stop(str(e.code)) from None
    except OSError as e:
        raise Stop("cannot read %s: %s" % (e.filename or elf, e.strerror)) from None
    if server_ip != "127.0.0.1" or sam_port != SAM_PORT or geo_port != GEO_PORT:
        blocks = mp_tss.with_server(blocks, server_ip, sam_port, geo_port)
    data = mp_tss.crypt(bf, iv, mp_tss.pack(blocks), "ofb", False)
    tmp = out + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, out)


def env_lines(server_ip, tss, tus, name, p2p_port=None, relay=False, signaling_port=None):
    env = mp_play.game_env({}, server_ip, tss, tus, name, p2p_port, signaling_port or SIGNALING_PORT, relay,
                           game_log=False)
    unknown = set(env) - set(MANAGED)
    if unknown:
        raise RuntimeError("mp_play.game_env sets %s, which the node does not manage" % sorted(unknown))
    return ["%s=%s" % (k, env.get(k, "")) for k in MANAGED]


def write_env(folder, lines):
    """game.env, whole or not at all: the game waits for it to appear."""
    tmp = os.path.join(folder, ENV_FILE + ".new")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(line + "\n" for line in lines))
    os.replace(tmp, os.path.join(folder, ENV_FILE))


def resolve(host):
    host = (host or "").strip()
    if not host:
        raise Stop("no server: the host's address goes in the launcher's Multiplayer tab")
    try:
        return mp_play.server_address(host)
    except (OSError, UnicodeError):
        raise Stop("cannot find %s: is the address right?" % host) from None


def main(argv):
    ap = argparse.ArgumentParser(description="God of War: Ascension's multiplayer, as the game starts it.")
    ap.add_argument("role", choices=("auto", "join", "host"))
    ap.add_argument("--server", help="join: the host's address")
    ap.add_argument("--name", required=True, help="the player's online id")
    ap.add_argument("--elf", required=True, help="the player's GOWA.elf")
    ap.add_argument("--dir", required=True, help="where the TSS, the TUS data, game.env and the log go")
    ap.add_argument("--relay", action="store_true", help="the game's datagrams always relayed (host or nodes)")
    ap.add_argument("--p2p-port", type=int, help="the UDP port peers reach this game at (3658)")
    ap.add_argument("--mode", type=int, help="host: the game mode of every Quick Play match")
    ap.add_argument("--players", type=int, help="host: Quick Play waits for this many players")
    a = ap.parse_args(argv)
    os.makedirs(a.dir, exist_ok=True)
    for n in (ENV_FILE, ERROR_FILE):
        try:
            os.remove(os.path.join(a.dir, n))
        except FileNotFoundError:
            pass
    log_file = open(os.path.join(a.dir, LOG_FILE), "w", encoding="utf-8")

    def log(text):
        line = time.strftime("%H:%M:%S ") + text
        log_file.write(line + "\n")
        log_file.flush()

    try:
        return run(a, log)
    except Stop as e:
        log("stopped: %s" % e)
        with open(os.path.join(a.dir, ERROR_FILE), "w", encoding="utf-8", newline="\n") as f:
            f.write("%s\n" % e)
        return 2
    finally:
        log_file.close()


def run(a, log):
    name = clean_online_id(a.name)
    if not name:
        raise Stop("\"%s\" is not an online id: 3-16 letters, digits, - and _, starting with a letter" % a.name)
    if a.role == "auto":
        return auto(a, name, log)
    server_ip = "127.0.0.1" if a.role == "host" else resolve(a.server)
    tss = os.path.join(a.dir, "tss.bin")
    build_tss(a.elf, tss, server_ip)
    log("%s as %s: TSS %s, matchmaker %s:%d" % (a.role, name, tss, server_ip, SAM_PORT))
    lines = env_lines(server_ip, tss, os.path.join(a.dir, "np_tus"), name, a.p2p_port, a.relay)
    if a.role == "join":
        write_env(a.dir, lines)     # the game goes on now; what follows is only for the log
        if not wait_port(server_ip, SAM_PORT, 3.0):
            log("%s:%d does not answer yet: not hosting, or a firewall or router in the way" % (server_ip, SAM_PORT))
        return 0
    return host(a, log, lines)


def wait_port(ip, port, timeout):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def forever():
    while True:
        time.sleep(3600)


def host(a, log, lines, wait=forever):
    import mp_sam  # noqa: E402
    import np_signaling_server  # noqa: E402
    try:
        sam = mp_sam.start("0.0.0.0", SAM_PORT, GEO_PORT, a.mode, log=lambda t: log("[sam] " + t), players=a.players)
    except OSError as e:
        raise Stop("ports %d and %d are taken (another game hosting here?): %s" % (SAM_PORT, GEO_PORT, e.strerror)) \
            from None
    try:
        sig = np_signaling_server.start("0.0.0.0", SIGNALING_PORT, lambda t: log("[signaling] " + t))
    except OSError as e:
        sam.stop()
        raise Stop("port %d is taken (another game hosting here?): %s" % (SIGNALING_PORT, e.strerror)) from None
    log("hosting: matchmaker %d, geo %d, signaling %d (TCP and UDP) on every address" % (SAM_PORT, GEO_PORT,
                                                                                          SIGNALING_PORT))
    write_env(a.dir, lines)
    try:
        wait()
    finally:
        sam.stop()
        sig.stop()
    return 0


def free_udp(start, tries=10):
    """The first UDP port from start that nothing on this PC holds now."""
    for port in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    return start


def auto(a, name, log, wait=None):
    """Multiplayer with no host: this PC's node (mp_p2p.py). Its ports on this PC are the usual ones, or any when
    another game's node has them (two games on one PC: the second one's P2P port is 3659 or later)."""
    import asyncio
    import mp_p2p  # noqa: E402

    async def go():
        node = mp_p2p.Node(name, log, a.p2p_port or 3658, dht_cache=os.path.join(a.dir, "dht-nodes.json"), **P2P)
        try:
            ports = await node.start(SAM_PORT, GEO_PORT, SIGNALING_PORT)
        except OSError as e:
            raise Stop("the node could not start: %s" % e.strerror) from None
        if not a.p2p_port:
            node.p2p_port = free_udp(3658 if ports[0] == SAM_PORT else 3659)
        tss = os.path.join(a.dir, "tss.bin")
        build_tss(a.elf, tss, "127.0.0.1", ports[0], ports[1])
        log("auto as %s: TSS %s, matchmaker 127.0.0.1:%d, P2P port %d" % (name, tss, ports[0], node.p2p_port))
        write_env(a.dir, env_lines("127.0.0.1", tss, os.path.join(a.dir, "np_tus"), name, node.p2p_port, a.relay,
                                   ports[2]))
        try:
            if wait:
                await wait(node)
            else:
                while True:
                    await asyncio.sleep(3600)
        finally:
            node.close()
        return 0

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
