"""Tools for a mod's files (docs/MODDING.md).

    modtools.py textures <the mod's textures folder> [--dry-run]
    modtools.py patch <the mod's whole file> <the entry> <the mod's archive folder> [--game <the game's folder>]

textures: pictures that are one file byte for byte, kept once. The first by name stays; each other one's id goes
into aliases.txt in the folder, with the id of the one that stays, and its file is removed. Pictures not named by an
id, and aliases.txt's own lines, are left as they are.

patch: a .PATCH of the entry (its name in the archives, /WAD/PS3_BE/R_HERO00.AS) in the form the game's updates
bring theirs: the ranges the mod's file has in common with the game's, at the same place, taken from the game's own,
the rest from the patch. The game puts it over its file as it loads it. Written into the archive folder at the
entry's path, with <entry>.PATCH.base beside it: the game's file it is made for (its size and SHA-1), which
modpack.py checks, leaving the patch out for a game whose file is another. The game's file is the newest update's
that brings it whole, else the disc's: --game names the disc's PS3_GAME folder (default the tree's vfs\\PS3_GAME) and
--updates the updates' USRDIR (default the tree's gamedata\\dev_hdd0\\game\\<title>\\USRDIR).

The game's patch (version 4): u16 version, u16 n, n steps of (u32 from, u32 length), then the patch's own data. A
step with the top bit of `from` set takes `length` bytes of the patch's own data, from the offset the other bits give;
any other takes them from the game's file at `from`. The file is the steps' bytes one after the other.
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gametext as gt  # noqa: E402

PATCH_VERSION = 4
OWN = 0x80000000
BLOCK = 4096        # compared whole first, then in pieces of GRAIN where they differ
GRAIN = 64
MIN_COPY = 32       # a stretch in common shorter than this between two of the patch's own goes in with them


class ModError(Exception):
    pass


# ---------------------------------------------------------------------------
# patches
# ---------------------------------------------------------------------------

def make_patch(base, target, grain=GRAIN):
    """The .PATCH that turns base into target."""
    steps = []            # [from, length] with OWN on the patch's own
    own = bytearray()
    bv, tv = memoryview(base), memoryview(target)

    def take_base(at, n):
        if steps and not steps[-1][0] & OWN and steps[-1][0] + steps[-1][1] == at:
            steps[-1][1] += n
        else:
            steps.append([at, n])

    def take_own(at, n):
        if steps and steps[-1][0] & OWN:
            steps[-1][1] += n
        else:
            steps.append([OWN | len(own), n])
        own.extend(tv[at:at + n])

    common = min(len(base), len(target))
    for i in range(0, common, BLOCK):
        j = min(i + BLOCK, common)
        if bv[i:j] == tv[i:j]:
            take_base(i, j - i)
            continue
        for k in range(i, j, grain):
            e = min(k + grain, j)
            if bv[k:e] == tv[k:e]:
                take_base(k, e - k)
            else:
                take_own(k, e - k)
    if len(target) > common:
        take_own(common, len(target) - common)
    # a short stretch in common between two own ones: own too (a step costs 8 bytes and a seek)
    merged, data, pos = [], bytearray(), 0
    for k, (frm, n) in enumerate(steps):
        short = (not frm & OWN and n < MIN_COPY and 0 < k < len(steps) - 1 and steps[k - 1][0] & OWN and
                 steps[k + 1][0] & OWN)
        if frm & OWN or short:
            chunk = own[frm & ~OWN:(frm & ~OWN) + n] if frm & OWN else bv[frm:frm + n]
            if merged and merged[-1][0] & OWN:
                merged[-1][1] += n
            else:
                merged.append([OWN | len(data), n])
            data.extend(chunk)
        else:
            merged.append([frm, n])
        pos += n
    if len(merged) > 0xFFFF:
        if grain >= BLOCK:
            raise ModError("the files differ in too many places for one patch (%d steps)" % len(merged))
        return make_patch(base, target, grain * 4)
    out = bytearray(struct.pack(">HH", PATCH_VERSION, len(merged)))
    for frm, n in merged:
        out += struct.pack(">II", frm, n)
    return bytes(out + data)


def apply_patch(base, patch):
    """The file a .PATCH makes of base, as the game makes it."""
    ver, n = struct.unpack(">HH", patch[:4])
    if ver != PATCH_VERSION:
        raise ModError("a patch of version %d" % ver)
    start = 4 + 8 * n
    out = bytearray()
    for i in range(n):
        frm, size = struct.unpack(">II", patch[4 + 8 * i:12 + 8 * i])
        if frm & OWN:
            a = start + (frm & ~OWN)
            if a + size > len(patch):
                raise ModError("step %d reads past the patch's data" % i)
            out += patch[a:a + size]
        else:
            if frm + size > len(base):
                raise ModError("step %d reads past the game's file (%d of %d)" % (i, frm + size, len(base)))
            out += base[frm:frm + size]
    return bytes(out)


def patch_summary(patch):
    """(steps, bytes of the game's file it takes, bytes of its own)."""
    n = struct.unpack(">H", patch[2:4])[0]
    from_base = own = 0
    for i in range(n):
        frm, size = struct.unpack(">II", patch[4 + 8 * i:12 + 8 * i])
        if frm & OWN:
            own += size
        else:
            from_base += size
    return n, from_base, own


def base_text(entry, base):
    """<entry>.PATCH.base: the game's file a patch is made for."""
    return "entry %s\nsize %d\nsha1 %s\n" % (entry, len(base), hashlib.sha1(base).hexdigest())


def read_base_text(text):
    out = {}
    for ln in text.splitlines():
        k, _, v = ln.strip().partition(" ")
        if k and not k.startswith("#"):
            out[k] = v.strip()
    return out


def base_matches(info, base):
    """Why base is not the file the .PATCH.base names, or None when it is."""
    try:
        size = int(info.get("size", "-1"))
    except ValueError:
        size = -1
    if size != len(base):
        return "made for a file of %s bytes, the game's has %d" % (info.get("size", "?"), len(base))
    if info.get("sha1", "").lower() != hashlib.sha1(base).hexdigest():
        return "made for another copy of the file (its SHA-1 differs)"
    return None


def newest_whole(entry, disc=None, updates=None):
    """(where, bytes) of the game's own file for an entry, as a .PATCH of it is put over: the newest update that brings
    it whole (TPPS<n> down to TPPS), else the disc's archive that has it. None when neither has it."""
    if updates and os.path.isfile(os.path.join(updates, "PATCHES")):
        n = gt.patch_count(updates)
        for k in range(n, -1, -1):
            arc = os.path.join(updates, "TPPS%s.PSARC" % (k or ""))
            if os.path.isfile(arc) and entry in gt.psarc_names(arc):
                return os.path.basename(arc), gt.psarc_read(arc, {entry})[entry]
    if disc and os.path.isdir(disc):
        for f in sorted(os.listdir(disc)):
            p = os.path.join(disc, f)
            if f.upper().endswith(".PSARC") and not f.upper().startswith("TPPS") and os.path.isfile(p):
                if entry in gt.psarc_names(p):
                    return f, gt.psarc_read(p, {entry})[entry]
    return None


def entry_name(name):
    n = "/" + name.replace("\\", "/").lstrip("/")
    return n.upper()


def cmd_patch(args):
    entry = entry_name(args.entry)
    if entry.endswith(".PATCH"):
        raise ModError("the entry is the game's file's name, without .PATCH")
    disc = os.path.join(args.game or os.path.join(gt.ROOT, "vfs", "PS3_GAME"), "USRDIR")
    updates = args.updates or next((u for u in (os.path.join(gt.ROOT, "gamedata", "dev_hdd0", "game", t, "USRDIR")
                                                for t in gt.TITLES)
                                    if os.path.isfile(os.path.join(u, "PATCHES"))), None)
    found = newest_whole(entry, disc, updates)
    if not found:
        raise ModError("neither the game's archives (%s) nor its updates (%s) have %s" % (disc, updates, entry))
    where, base = found
    with open(args.file, "rb") as f:
        target = f.read()
    patch = make_patch(base, target)
    if apply_patch(base, patch) != target:
        raise ModError("the patch does not give the file back (a fault in this tool)")
    out = os.path.join(args.archive, *entry.lstrip("/").split("/")) + ".PATCH"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(patch)
    with open(out + ".base", "w", encoding="utf-8", newline="\n") as f:
        f.write(base_text(entry, base))
    n, from_base, own = patch_summary(patch)
    print("%s: %d steps, %.1f MB from the game's (%s), %.1f MB of its own: %.1f MB for a file of %.1f MB"
          % (os.path.relpath(out, args.archive), n, from_base / 1048576.0, where, own / 1048576.0,
             len(patch) / 1048576.0, len(target) / 1048576.0))
    return 0


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------

def picture_id(name):
    """The id a picture's file name gives (sixteen hex digits, then '_' or '.'), or None."""
    if len(name) < 20 or not name.lower().endswith(".png") or name[16] not in "._":
        return None
    try:
        int(name[:16], 16)
    except ValueError:
        return None
    return name[:16].lower()


def fold_textures(folder, dry_run=False):
    """Pictures that are one file kept once; (kept, folded, the lines added to aliases.txt)."""
    by_content = {}
    pictures = []
    for d, _, fs in os.walk(folder):
        for f in sorted(fs):
            pid = picture_id(f)
            if pid:
                pictures.append((os.path.relpath(os.path.join(d, f), folder).replace(os.sep, "/"), pid))
    pictures.sort(key=lambda t: t[0].lower())
    lines, gone = [], []
    seen_ids = {}
    for rel, pid in pictures:
        with open(os.path.join(folder, rel), "rb") as f:
            h = hashlib.sha1(f.read()).hexdigest()
        if pid in seen_ids:          # a second file for one id: the first one wins in the game too; leave it
            continue
        seen_ids[pid] = rel
        if h in by_content:
            keep_id = by_content[h][1]
            lines.append("%s %s" % (pid, keep_id))
            gone.append(rel)
        else:
            by_content[h] = (rel, pid)
    if lines and not dry_run:
        path = os.path.join(folder, "aliases.txt")
        old = open(path, encoding="utf-8-sig").read() if os.path.isfile(path) else ""
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            if old:
                f.write(old if old.endswith("\n") else old + "\n")
            else:
                f.write("# <texture id> <the picture it takes: the id of one in this folder, or a file here>\n")
            for ln in lines:
                f.write(ln + "\n")
        for rel in gone:
            os.remove(os.path.join(folder, rel))
    return len(by_content), len(gone), lines


def cmd_textures(args):
    if not os.path.isdir(args.folder):
        raise ModError("no folder %s" % args.folder)
    before = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(args.folder) for f in fs)
    kept, folded, lines = fold_textures(args.folder, args.dry_run)
    after = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(args.folder) for f in fs)
    print("%d pictures, %d more files of the same ones %s (%s aliases.txt lines)%s" % (
        kept, folded, "found" if args.dry_run else "folded into aliases.txt", len(lines),
        "" if args.dry_run else ": %.1f MB -> %.1f MB" % (before / 1048576.0, after / 1048576.0)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="modtools.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("textures", help="fold pictures that are one file into aliases.txt")
    t.add_argument("folder")
    t.add_argument("--dry-run", action="store_true", help="say what it would do, change nothing")
    q = sub.add_parser("patch", help="a .PATCH of an entry against the game's own file, and its .base")
    q.add_argument("file", help="the mod's whole file")
    q.add_argument("entry", help="its name in the archives: /WAD/PS3_BE/R_HERO00.AS")
    q.add_argument("archive", help="the mod's archive folder")
    q.add_argument("--game", help="the game's PS3_GAME folder (default: the tree's)")
    q.add_argument("--updates", help="the game's updates' USRDIR (default: the tree's gamedata)")
    a = p.parse_args(argv)
    try:
        return cmd_patch(a) if a.cmd == "patch" else cmd_textures(a)
    except (ModError, OSError, gt.TextError) as e:
        print("modtools: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
