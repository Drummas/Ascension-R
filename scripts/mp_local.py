"""Multiplayer on this PC alone (docs/notes/2026-11-22-multiplayer-phase3.md): builds our TSS, starts the game
signed in with a ticket of our own, every name it looks up pointed at 127.0.0.1 and nothing let past this PC, and runs
our matchmaker (scripts/mp_sam.py) where our MatchConfig sends the game (SAM 10070, geo 10012) and the runtime's
signaling server (ps3recomp/tools/np_signaling_server.py, 36101) for the players' peer-to-peer connections.

    mp_local.py [--exe build/Ascension-R.exe] [--out build/online] [--name <online id>] [--mode N] [--solo]
                [--relay] [--two --hdd0 <the game's dev_hdd0> [--name-b PlayerB]] [-- <game arguments>]

On the title screen, right picks Multi-Player. A first profile starts the multiplayer tutorial; finished (or with a
profile that says so in TUS slot 1), the lobby's Quick Play searches, and our matchmaker puts the players into a game
world. The games connect to each other through the signaling server and play the match peer to peer; at its end both
go back to the lobby, and the next match takes the next level of the mode.

--two starts a second game beside the first, as another player: online id --name-b, its own dev_hdd0 in <out>/hdd0-b
(its own home folder and -DATA folders, copies of the first's; the game folders joined to the first's), its own cache
partition (<out>/hdd1-b), its own shader cache (<out>/shader-b), P2P port 3659, no mods, and the other half of the
processors. Both search, and the matchmaker puts the two into one world. A second player who has no TUS profile yet
gets a copy of the first's. The games here use <out>/hdd1 as their cache partition, not the one normal play uses:
two games writing one FIOS disc cache have broken it, and every lobby entry then stalled (phase 4 note).

--solo reserves a world for one player; --mode N puts every Quick Play match in game mode N (10 is FVS2, two players);
--relay sends the players' datagrams through the signaling server's relay. The game's own log is on
(GOWA_GAME_LOG=1); the matchmaker writes <out>/sam.log. Players on other machines: scripts/mp_server.py and
scripts/mp_play.py (docs/notes/2026-11-22-multiplayer-phase4.md).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mp_play  # noqa: E402
import mp_sam  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "ps3recomp", "tools"))
import np_signaling_server  # noqa: E402


def clean_online_id(name):
    """The runtime's rule (np_psnr.c): 3-16 letters, digits, - and _, starting with a letter; else None."""
    s = "".join(c for c in (name or "") if c.isascii() and (c.isalnum() or c in "-_"))[:16]
    return s if len(s) >= 3 and s[0].isalpha() else None


def is_link(path):
    """A symlink or (Windows) a junction: removing it leaves its target alone."""
    if os.path.islink(path):
        return True
    isj = getattr(os.path, "isjunction", None)
    return bool(isj and isj(path))


def second_hdd0(first, dest):
    """dest as a dev_hdd0 for a second player: its own home (copied once), its own copy of each game's -DATA folder
    (the game writes there: DCDS state), and the installed game folders joined to first's (read only)."""
    os.makedirs(os.path.join(dest, "game"), exist_ok=True)
    if not os.path.isdir(os.path.join(dest, "home")) and os.path.isdir(os.path.join(first, "home")):
        shutil.copytree(os.path.join(first, "home"), os.path.join(dest, "home"), symlinks=True)
    games = os.path.join(first, "game")
    for name in (os.listdir(games) if os.path.isdir(games) else []):
        link = os.path.join(dest, "game", name)
        src = os.path.realpath(os.path.join(games, name))
        if name.upper().endswith("-DATA"):
            # Not shared: two games should not write one file. An earlier link goes (not its target).
            if is_link(link):
                os.rmdir(link) if os.name == "nt" else os.unlink(link)
            if not os.path.exists(link):
                shutil.copytree(src, link)
            continue
        if os.path.lexists(link):
            continue
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(src, link)
        else:
            os.symlink(src, link)


def second_shader_cache(exe, dest):
    """A shader cache of the second game's own (a copy of the first's, made once): two games appending to one
    journal spoil it. Returns the file graphics.shader_cache names."""
    os.makedirs(dest, exist_ok=True)
    src_dir = os.path.dirname(os.path.abspath(exe))
    for name in os.listdir(src_dir):
        if name.startswith("d3d12_shader_cache.bin") and not os.path.exists(os.path.join(dest, name)):
            shutil.copy2(os.path.join(src_dir, name), os.path.join(dest, name))
    return os.path.join(dest, "d3d12_shader_cache.bin")


def pin_half(proc, which):
    """Two games on one PC: each on its own half of the logical processors, so they share the machine evenly."""
    if os.name != "nt":
        return
    import ctypes
    n = os.cpu_count() or 2
    half = max(1, n // 2)
    mask = ((1 << half) - 1) << (0 if which == 0 else n - half)
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x0200 | 0x0400, False, proc.pid)   # PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION
    if h:
        k32.SetProcessAffinityMask(h, ctypes.c_size_t(mask))
        k32.CloseHandle(h)


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
    ap.add_argument("--relay", action="store_true", help="the players' datagrams through the signaling server's relay")
    a = ap.parse_args(argv)
    name_a = clean_online_id(a.name) or clean_online_id(os.environ.get("USERNAME") or os.environ.get("USER"))
    name_b = clean_online_id(a.name_b)
    if a.two and not a.hdd0:
        ap.error("--two needs --hdd0 (the dev_hdd0 the first game uses)")
    if a.two and (not name_b or name_b == name_a):
        ap.error("--name-b must be a valid online id other than the first player's")
    tss = mp_play.build_tss(a.out, "127.0.0.1")
    tus = os.path.join(a.out, "np_tus")

    log_file = open(os.path.join(a.out, "sam.log"), "a", encoding="utf-8")

    def log(text):
        line = time.strftime("%H:%M:%S ") + text
        log_file.write(line + "\n")
        log_file.flush()
        if not text.startswith(("<-", "  ->")):
            print("[mp_sam] " + text, flush=True)

    srv = mp_sam.start(mode=a.mode, solo=a.solo, log=log)
    sig = np_signaling_server.start(port=np_signaling_server.DEFAULT_PORT, log=lambda t: print("[signaling] " + t, flush=True))
    env = mp_play.game_env(os.environ, "127.0.0.1", tss, tus, a.name or None, None, sig.port, a.relay)
    # A cache partition (/dev_hdd1: the game's FIOS disc cache) of these runs' own, one per game: two games writing
    # one cache have broken it, and every lobby entry after that stalled on a streamed read.
    env["PS3_HDD1_ROOT"] = os.path.abspath(os.path.join(a.out, "hdd1")).replace("\\", "/")
    print("[mp_local] TSS %s, TUS %s, matchmaker on SAM %d, geo %d, signaling %d%s" % (
        tss, tus, srv.ports[0], srv.ports[1], sig.port, ", relay always" if a.relay else ""), flush=True)
    games = []
    try:
        first = list(rest)
        if a.two:
            first += ["--set", "paths.hdd0=" + os.path.abspath(a.hdd0).replace("\\", "/")]
        games.append(subprocess.Popen([a.exe] + first, cwd=os.path.dirname(a.exe), env=env))
        if a.two:
            pin_half(games[0], 0)
            hdd0_b = os.path.join(a.out, "hdd0-b")
            second_hdd0(a.hdd0, hdd0_b)
            if name_a:
                share_tus_profile(tus, name_a, name_b)
            env_b = dict(env, PS3_NP_ONLINE_ID=name_b, PS3_NET_P2P_PORT="3659",
                         PS3_HDD1_ROOT=os.path.abspath(os.path.join(a.out, "hdd1-b")).replace("\\", "/"))
            print("[mp_local] second player %s, dev_hdd0 %s, P2P port 3659, no mods, its own shader cache" %
                  (name_b, hdd0_b), flush=True)
            time.sleep(3)
            # No mods for the second game: both would pack them into the one build/mods/.built while the first has
            # its archive open, and two games starting that way have hung on their first load.
            cache_b = second_shader_cache(a.exe, os.path.join(a.out, "shader-b"))
            games.append(subprocess.Popen([a.exe] + rest + ["--set", "paths.hdd0=" + hdd0_b.replace("\\", "/"),
                                                            "--set", "mods.use=off",
                                                            "--set", "graphics.shader_cache=" + cache_b.replace("\\", "/")],
                                          cwd=os.path.dirname(a.exe), env=env_b))
            pin_half(games[1], 1)
        rc = 0
        for g in games:
            rc = g.wait() or rc
    finally:
        for g in games:
            if g.poll() is None:
                g.kill()
        srv.stop()
        sig.stop()
        log_file.close()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
