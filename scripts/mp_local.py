"""Multiplayer on this PC alone, as far as it goes (docs/notes/2026-11-22-multiplayer-phase2.md): builds our TSS,
starts the game signed in with a ticket of our own, every name it looks up pointed at 127.0.0.1 and nothing let
past this PC, and runs our matchmaker (scripts/mp_sam.py) where our MatchConfig sends the game (SAM 10070, geo 10012).

    mp_local.py [--exe build/Ascension-R.exe] [--out build/online] [--name <online id>] [--mode N] [--solo]
                [--two --hdd0 <the game's dev_hdd0> [--name-b PlayerB]] [-- <game arguments>]

On the title screen, right picks Multi-Player. A first profile starts the multiplayer tutorial; finished (or with a
profile that says so in TUS slot 1), the lobby's Quick Play searches, and our matchmaker puts the players into a game
world. The game then starts the match's peer-to-peer connections, which NP signaling does not make yet (phase 3).

--two starts a second game beside the first, as another player: online id --name-b, its own dev_hdd0 in <out>/hdd0-b
(its own home folder, a copy of the first's; the game folders joined to the first's), P2P port 3659. Both search, and
the matchmaker puts the two into one world. A second player who has no TUS profile yet gets a copy of the first's.

--solo reserves a world for one player; --mode N puts every Quick Play match in game mode N (10 is FVS2, two players).
The game's own log is on (GOWA_GAME_LOG=1); the matchmaker writes <out>/sam.log.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_sam  # noqa: E402
import mp_tss  # noqa: E402


def clean_online_id(name):
    """The runtime's rule (np_psnr.c): 3-16 letters, digits, - and _, starting with a letter; else None."""
    s = "".join(c for c in (name or "") if c.isascii() and (c.isalnum() or c in "-_"))[:16]
    return s if len(s) >= 3 and s[0].isalpha() else None


def second_hdd0(first, dest):
    """dest as a dev_hdd0 for a second player: its own home (copied once), the game folders joined to first's."""
    os.makedirs(os.path.join(dest, "game"), exist_ok=True)
    if not os.path.isdir(os.path.join(dest, "home")) and os.path.isdir(os.path.join(first, "home")):
        shutil.copytree(os.path.join(first, "home"), os.path.join(dest, "home"), symlinks=True)
    games = os.path.join(first, "game")
    for name in (os.listdir(games) if os.path.isdir(games) else []):
        link = os.path.join(dest, "game", name)
        if os.path.lexists(link):
            continue
        target = os.path.realpath(os.path.join(games, name))
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(target, link)
        else:
            os.symlink(target, link)


def share_tus_profile(tus, first, second):
    """Give the second player the first one's TUS slots where it has none (the tutorial done once)."""
    for comm in (os.listdir(tus) if os.path.isdir(tus) else []):
        src, dst = os.path.join(tus, comm, first), os.path.join(tus, comm, second)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)


def main(argv):
    rest = []
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    ap = argparse.ArgumentParser(description="God of War: Ascension's multiplayer against stand-ins on this PC.")
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "Ascension-R.exe"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "online"))
    ap.add_argument("--name", default="", help="the online id (else the launcher's or the OS login)")
    ap.add_argument("--mode", type=int, help="the game mode of every Quick Play match (10: FVS2, two players)")
    ap.add_argument("--solo", action="store_true", help="a game world for one player")
    ap.add_argument("--two", action="store_true", help="a second game beside the first, as another player")
    ap.add_argument("--hdd0", help="with --two: the dev_hdd0 the first game uses")
    ap.add_argument("--name-b", default="PlayerB", help="with --two: the second player's online id")
    a = ap.parse_args(argv)
    name_a = clean_online_id(a.name) or clean_online_id(os.environ.get("USERNAME") or os.environ.get("USER"))
    name_b = clean_online_id(a.name_b)
    if a.two and not a.hdd0:
        ap.error("--two needs --hdd0 (the dev_hdd0 the first game uses)")
    if a.two and (not name_b or name_b == name_a):
        ap.error("--name-b must be a valid online id other than the first player's")
    os.makedirs(a.out, exist_ok=True)
    tss = os.path.join(a.out, "tss.bin")
    mp_tss.main(["build", os.path.join(ROOT, "online", "tss"), tss])
    tus = os.path.join(a.out, "np_tus")
    env = dict(os.environ, PS3_NET_ONLINE="1", PSNR_SERVER="127.0.0.1:36100", PS3_NP_TEST_TICKET="1",
               PS3_NP_TSS_FILE=tss, PS3_NP_TUS_DIR=tus,
               PS3_NET_HOSTS="*=127.0.0.1", PS3_NET_LOOPBACK_ONLY="1", GOWA_GAME_LOG="1")
    if a.name:
        env["PS3_NP_ONLINE_ID"] = a.name

    log_file = open(os.path.join(a.out, "sam.log"), "a", encoding="utf-8")

    def log(text):
        line = time.strftime("%H:%M:%S ") + text
        log_file.write(line + "\n")
        log_file.flush()
        if not text.startswith(("<-", "  ->")):
            print("[mp_sam] " + text, flush=True)

    srv = mp_sam.start(mode=a.mode, solo=a.solo, log=log)
    print("[mp_local] TSS %s, TUS %s, matchmaker on SAM %d, geo %d" % (tss, tus, srv.ports[0], srv.ports[1]), flush=True)
    games = []
    try:
        first = list(rest)
        if a.two:
            first += ["--set", "paths.hdd0=" + os.path.abspath(a.hdd0).replace("\\", "/")]
        games.append(subprocess.Popen([a.exe] + first, cwd=os.path.dirname(a.exe), env=env))
        if a.two:
            hdd0_b = os.path.join(a.out, "hdd0-b")
            second_hdd0(a.hdd0, hdd0_b)
            if name_a:
                share_tus_profile(tus, name_a, name_b)
            env_b = dict(env, PS3_NP_ONLINE_ID=name_b, PS3_NET_P2P_PORT="3659")
            print("[mp_local] second player %s, dev_hdd0 %s, P2P port 3659" % (name_b, hdd0_b), flush=True)
            time.sleep(3)
            games.append(subprocess.Popen([a.exe] + rest + ["--set", "paths.hdd0=" + hdd0_b.replace("\\", "/")],
                                          cwd=os.path.dirname(a.exe), env=env_b))
        rc = 0
        for g in games:
            rc = g.wait() or rc
    finally:
        for g in games:
            if g.poll() is None:
                g.kill()
        srv.stop()
        log_file.close()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
