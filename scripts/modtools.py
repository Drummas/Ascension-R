"""Tools for a mod's files (docs/MODDING.md).

    modtools.py textures <the mod's textures folder> [--dry-run]
    modtools.py patch <the mod's whole file> <the entry> <the mod's archive folder> [--game <the game's folder>]
    modtools.py extract <a folder> [--game <the game's PS3_GAME folder>] [--updates <its updates' USRDIR>]
    modtools.py upscale <the textures dump> <the mod's folder> [--scale 2] [--upscaler lanczos|"<command>"] [...]

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

extract: every DXT texture of the game's files (the disc's archives, its updates over them: an update's whole file,
or its .PATCH over the file it is made for), each as a DDS of its first level named as the dump names it,
<id>_<w>x<h>_<format>.dds: a dump of the whole game without playing it, for upscale. A texture's id is the one the
game gives it on the GPU (XXH64 of its first level); of its copies (the levels a level's WAD holds, the whole one its
stream holds) only the biggest is written: the port gives the others the same picture. Files written already are not
written again.

upscale: a mod of the textures in a dump (textures-dump, the Mods tab's Write out the game's textures) made bigger,
for this PC's own game: each colour texture, normal map and texture with transparency at --scale times its size,
as a DDS (BC1, or BC3 with alpha, with its chain) named by the texture's id, into <mod>\\textures. Masks, the font,
copies of the frame, one-colour and small ones are left out. A texture that repeats is padded with its other side
before upscaling, another with its own edge mirrored, so the edges come out right. The game's normal maps (AG: red
full, blue none, y in green, x in alpha) are rebuilt as normals, upscaled, normalised and packed back. Alpha is
upscaled on its own. Textures with the same texels are made once and the others named in aliases.txt. Pictures the
mod has already are not made again (--force). The upscaler: Lanczos built in, or the player's own as a command,
e.g. "realesrgan-ncnn-vulkan -i {in_dir} -o {out_dir} -s 4 -n realesrgan-x4plus" (a picture it gives bigger than
asked is brought to the size). Needs Pillow and NumPy (python -m pip install pillow numpy).

The game's patch (version 4): u16 version, u16 n, n steps of (u32 from, u32 length), then the patch's own data. A
step with the top bit of `from` set takes `length` bytes of the patch's own data, from the offset the other bits give;
any other takes them from the game's file at `from`. The file is the steps' bytes one after the other.
"""
import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys
import time

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
    if len(name) < 20 or not name.lower().endswith((".png", ".dds")) or name[16] not in "._":
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


# ---------------------------------------------------------------------------
# the game's textures, from its files (extract, and texture_copies.py)
# ---------------------------------------------------------------------------

DXT_FORMATS = {b"DXT1": 0x86, b"DXT3": 0x87, b"DXT5": 0x88}
_P1, _P2, _P3, _P4, _P5 = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63,
                           0x27D4EB2F165667C5)
_M64 = (1 << 64) - 1


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M64


def _xround(acc, lane):
    acc = (acc + lane * _P2) & _M64
    return (_rotl(acc, 31) * _P1) & _M64


def xxh64(data, seed=0):
    """XXH64, as its specification has it: what a texture's id is (ps3recomp's libs/video/rsx_tex_replace.h)."""
    n, p = len(data), 0
    if n >= 32:
        v1, v2, v3, v4 = (seed + _P1 + _P2) & _M64, (seed + _P2) & _M64, seed & _M64, (seed - _P1) & _M64
        lanes = struct.unpack_from("<%dQ" % (4 * (n // 32)), data, 0)
        for i in range(0, len(lanes), 4):
            v1 = _xround(v1, lanes[i])
            v2 = _xround(v2, lanes[i + 1])
            v3 = _xround(v3, lanes[i + 2])
            v4 = _xround(v4, lanes[i + 3])
        p = 32 * (n // 32)
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M64
        for v in (v1, v2, v3, v4):
            h ^= _xround(0, v)
            h = (h * _P1 + _P4) & _M64
    else:
        h = (seed + _P5) & _M64
    h = (h + n) & _M64
    while p + 8 <= n:
        h ^= _xround(0, struct.unpack_from("<Q", data, p)[0])
        h = (_rotl(h, 27) * _P1 + _P4) & _M64
        p += 8
    if p + 4 <= n:
        h ^= (struct.unpack_from("<I", data, p)[0] * _P1) & _M64
        h = (_rotl(h, 23) * _P2 + _P3) & _M64
        p += 4
    while p < n:
        h ^= (data[p] * _P5) & _M64
        h = (_rotl(h, 11) * _P1) & _M64
        p += 1
    h ^= h >> 33
    h = (h * _P2) & _M64
    h ^= h >> 29
    h = (h * _P3) & _M64
    h ^= h >> 32
    return h


def tex_id(level, fmt, w, h):
    """A texture's id: XXH64 of its first level as the game has it, the seed its format byte, width and height."""
    return xxh64(level, (fmt & 0xFF) << 48 | (w & 0xFFFFFF) << 24 | (h & 0xFFFFFF))


def wad_entries(d):
    """[(name, type, offset of the data, size)] of a WAD-form file (a .WAD, an .AS)."""
    o, out = 0, []
    while o + 64 <= len(d):
        tag, fl, size = struct.unpack(">HHI", d[o:o + 8])
        if tag == 1:
            out.append((d[o + 8:o + 64].split(b"\x00")[0].decode("latin-1"), fl, o + 64, size))
        o = (o + 64 + size + 15) & ~15
    return out


def level_bytes(w, h, bpb):
    return max(1, w // 4) * max(1, h // 4) * bpb


def chain_bytes(w, h, bpb):
    t = 0
    while True:
        t += level_bytes(w, h, bpb)
        if w == 1 and h == 1:
            return t
        w, h = max(1, w // 2), max(1, h // 2)


def first_level(w, h, bpb, n):
    """The first level an entry's n bytes of levels start from: 0 when they hold level 0, else the level whose chain
    down to 1x1 they are; None when no level fits."""
    if n >= level_bytes(w, h, bpb):
        return 0
    for k in range(1, 16):
        lw, lh = max(1, w >> k), max(1, h >> k)
        if n >= level_bytes(lw, lh, bpb) and abs(chain_bytes(lw, lh, bpb) - n) <= 64:
            return k
        if lw == 1 and lh == 1:
            break
    return None


def texture_copies(d, ts):
    """(name, format byte, width, height, first level's bytes) of each copy of each DXT texture entry of a WAD-form
    file: the levels the entry holds (all, or from level 2 down for a level's WAD whose stream has the rest), and the
    whole first level its stream (ts, the .TS beside the .WAD or .AS) holds at the entry's offset. Each reaches the
    GPU with an id of its own."""
    for name, fl, at, size in wad_entries(d):
        if fl != 0x16 or size < 208 or not name.upper().startswith("TX"):
            continue
        b = d[at:at + size]
        off, nlev = struct.unpack_from(">II", b, 60)
        h, w = struct.unpack_from("<II", b, 80 + 12)
        fmt = DXT_FORMATS.get(bytes(b[80 + 84:80 + 88]))
        if not fmt or not w or not h or w > 8192 or h > 8192:
            continue
        bpb = 8 if fmt == 0x86 else 16
        k = first_level(w, h, bpb, size - 208)
        if k is not None:
            lw, lh = max(1, w >> k), max(1, h >> k)
            yield name, fmt, lw, lh, bytes(b[208:208 + level_bytes(lw, lh, bpb)])
        if k != 0 and ts is not None and off < 0xFFFFFFF0 and nlev <= 16 and off + level_bytes(w, h, bpb) <= len(ts):
            yield name, fmt, w, h, bytes(ts[off:off + level_bytes(w, h, bpb)])


def update_files(updates):
    """Each .AS, .WAD and .TS the updates bring, by its name in capitals: (archive, entry, whether a .PATCH), the newest
    update's (TPPS<n> over TPPS<n-1> ... over TPPS)."""
    out = {}
    if not updates or not os.path.isfile(os.path.join(updates, "PATCHES")):
        return out
    for k in range(0, gt.patch_count(updates) + 1):
        arc = os.path.join(updates, "TPPS%s.PSARC" % (k or ""))
        if not os.path.isfile(arc):
            continue
        for name in gt.psarc_names(arc):
            u = name.upper()
            if u.endswith((".AS", ".WAD", ".TS")):
                out[u] = (arc, name, False)
            elif u.endswith((".AS.PATCH", ".WAD.PATCH", ".TS.PATCH")):
                out[u[:-6]] = (arc, name, True)
    return out


def game_file(name, disc_arc, upd, disc, updates):
    """A file as the game reads it: an update's whole copy, or the newest update's .PATCH over the file it is made
    for, else the disc's. None when it cannot be had."""
    got = upd.get(name.upper())
    if got:
        arc, entry, patch = got
        data = gt.psarc_read(arc, {entry})[entry]
        if not patch:
            return data
        base = newest_whole(entry[:-6], disc, updates)
        return apply_patch(base[1], data) if base else None
    return gt.psarc_read(disc_arc, {name})[name] if disc_arc else None


def game_textures(disc, updates=None, log=print):
    """Every copy of every DXT texture in the game's files, as the game reads them (its updates over its disc): (file,
    texture name, format byte, width, height, first level's bytes). disc: the disc's USRDIR."""
    upd = update_files(updates)
    seen = set()
    arcs = sorted(f for f in os.listdir(disc) if f.upper().endswith(".PSARC") and not f.upper().startswith("TPPS"))
    t0 = time.time()
    for i, a in enumerate(arcs):
        p = os.path.join(disc, a)
        try:
            names = gt.psarc_names(p)
        except (OSError, gt.TextError) as e:
            log("  %s: left out (%s)" % (a, e))
            continue
        have = {n.upper(): n for n in names}
        for n in names:
            if not n.upper().endswith((".AS", ".WAD")) or n.upper() in seen:
                continue
            seen.add(n.upper())
            d = game_file(n, p, upd, disc, updates)
            tsu = os.path.splitext(n)[0].upper() + ".TS"
            ts = game_file(have.get(tsu, tsu), p if tsu in have else None, upd, disc, updates) \
                if tsu in have or tsu in upd else None
            if d is None:
                continue
            for c in texture_copies(d, ts):
                yield (n,) + c
        log("  %d/%d %s, %.0f s" % (i + 1, len(arcs), a, time.time() - t0))
    for u, (arc, entry, patch) in sorted(upd.items()):   # files only an update has
        if not u.endswith((".AS", ".WAD")) or u in seen:
            continue
        seen.add(u)
        d = game_file(entry[:-6] if patch else entry, None, upd, disc, updates)
        tsu = os.path.splitext(u)[0] + ".TS"
        ts = game_file(tsu, None, upd, disc, updates) if tsu in upd else None
        if d is not None:
            for c in texture_copies(d, ts):
                yield (entry,) + c


def dds_of_level(fmt, w, h, level):
    """A DDS of one DXT level, as the game has it."""
    cc = {0x86: b"DXT1", 0x87: b"DXT3", 0x88: b"DXT5"}[fmt]
    head = struct.pack("<4sIIIIIII", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, len(level), 0, 1)
    head += b"\0" * 44 + struct.pack("<II4sIIIII", 32, 0x4, cc, 0, 0, 0, 0, 0) + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    return head + level


def cmd_extract(args):
    game = args.game or os.path.join(gt.ROOT, "vfs", "PS3_GAME")
    disc = os.path.join(game, "USRDIR") if os.path.isdir(os.path.join(game, "USRDIR")) else game
    if not os.path.isdir(disc) or not any(f.upper().endswith(".PSARC") for f in os.listdir(disc)):
        raise ModError("no game's archives in %s (--game: the game's PS3_GAME folder)" % disc)
    updates = args.updates or next((u for u in (os.path.join(gt.ROOT, "gamedata", "dev_hdd0", "game", t, "USRDIR")
                                                for t in gt.TITLES)
                                    if os.path.isfile(os.path.join(u, "PATCHES"))), None)
    os.makedirs(args.out, exist_ok=True)
    print("the disc's archives in %s; its updates %s" % (disc, updates or "not found: the disc's textures alone"))
    # Each texture's biggest copies (its other copies take their pictures through the port's table of copies), each
    # written once as it comes, the smaller ones of a texture removed at the end.
    biggest, written, ids = {}, {}, set()
    t0 = time.time()
    for _, name, fmt, w, h, level in game_textures(disc, updates, log=print if args.verbose else lambda s: None):
        key = name.upper()
        area = w * h
        if area < biggest.get(key, 0):
            continue
        biggest[key] = area
        tid = "%016x" % tex_id(level, fmt, w, h)
        if tid in ids:
            continue
        ids.add(tid)
        path = os.path.join(args.out, "%s_%dx%d_%02X.dds" % (tid, w, h, fmt))
        written.setdefault(key, []).append((area, path))
        if not os.path.isfile(path):
            with open(path + ".part", "wb") as f:
                f.write(dds_of_level(fmt, w, h, level))
            os.replace(path + ".part", path)
    gone = 0
    for key, files in written.items():
        for area, path in files:
            if area < biggest[key] and os.path.isfile(path):
                os.remove(path)
                gone += 1
    kept = sum(1 for key, files in written.items() for area, path in files if area == biggest[key])
    print("%d textures, %d files of their biggest copies in %s (%d smaller copies left out), %.0f s" % (
        len(biggest), kept, args.out, gone, time.time() - t0))
    return 0


# ---------------------------------------------------------------------------
# upscale
# ---------------------------------------------------------------------------

DUMP_NAME = re.compile(r"^([0-9a-fA-F]{16})_(\d+)x(\d+)_([0-9A-Fa-f]{2})\.(?:png|dds)$", re.I)
# The game's textures that take a picture as RGBA (rsx_tex_replace.h): the 16-bit colour ones, A8R8G8B8, DXT1/3/5.
COLOUR_FORMATS = {0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x97, 0x9D, 0x9E}
KINDS = ("colour", "alpha", "normal")


def imaging():
    """Pillow and NumPy, which upscale needs and the Kit's own Python does not have."""
    try:
        import numpy
        from PIL import Image
    except ImportError:
        raise ModError("upscale needs Python with Pillow and NumPy: python -m pip install pillow numpy")
    if not hasattr(Image, "Resampling"):
        raise ModError("upscale needs Pillow 9.1 or newer: python -m pip install -U pillow")
    return numpy, Image


def texture_kind(a, fmt, w, h, min_side):
    """What a dumped texture is, for the upscale: 'colour', 'alpha' (it has transparency), 'normal' (an AG normal map:
    red full, blue none, the normal's y in green and its x in alpha), or why it is left out."""
    np, _ = imaging()
    if fmt & 0x20:
        return "left out: linear (a copy of the frame, a target)"
    if (fmt & 0x9F) not in COLOUR_FORMATS:
        return "left out: one or two channels (a mask, the font)"
    if min(w, h) < min_side:
        return "left out: smaller than %d" % min_side
    f = a.astype(np.float32)
    if float(f[..., :3].std(axis=(0, 1)).max()) < 2.0 and float(f[..., 3].std()) < 2.0:
        return "left out: one colour"
    r, g, b, al = (float(f[..., c].mean()) for c in range(4))
    if r > 230 and b < 30 and 40 < g < 215 and 40 < al < 215 and float(f[..., 3].std()) > 2.0:
        return "normal"
    if int(a[..., 3].min()) < 255:
        return "alpha"
    return "colour"


def tiles(a):
    """Whether a texture repeats: its opposite edges as alike as texels side by side within it. A repeating one is
    padded with its other side before upscaling, so its edges still meet; another with its own edge mirrored."""
    np, _ = imaging()
    f = a[..., :3].astype(np.float32)
    inner_h = float(np.abs(f[:, 1:] - f[:, :-1]).mean())
    inner_v = float(np.abs(f[1:] - f[:-1]).mean())
    seam_h = float(np.abs(f[:, 0] - f[:, -1]).mean())
    seam_v = float(np.abs(f[0] - f[-1]).mean())
    return seam_h <= 1.5 * inner_h + 2.0 and seam_v <= 1.5 * inner_v + 2.0


def resize_channel(ch, w, h):
    """A float32 channel to w x h, Lanczos."""
    np, Image = imaging()
    return np.asarray(Image.fromarray(ch.astype(np.float32), "F").resize((w, h), Image.Resampling.LANCZOS))


def lanczos_rgb(rgb, w, h):
    np, Image = imaging()
    return np.asarray(Image.fromarray(rgb, "RGB").resize((w, h), Image.Resampling.LANCZOS))


def run_upscaler(template, src, dst, scale):
    """The player's upscaler on one picture, or on a folder of them ({in_dir}, {out_dir}); {scale} is the scale."""
    cmd = template.replace("{in}", '"%s"' % src).replace("{out}", '"%s"' % dst).replace(
        "{in_dir}", '"%s"' % src).replace("{out_dir}", '"%s"' % dst).replace("{scale}", str(scale))
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if r.returncode:
        raise ModError("the upscaler stopped (%d): %s\n%s" % (r.returncode, cmd, r.stdout[-2000:]))


def write_dds(path, levels, alpha):
    """A DDS of the levels (Pillow images, level 0 first), BC3 (DXT5) with alpha, else BC1 (DXT1), by Pillow's own
    encoder, with the header that names the chain."""
    import io
    blocks = []
    pf = "DXT5" if alpha else "DXT1"
    for im in levels:
        b = io.BytesIO()
        im.save(b, "DDS", pixel_format=pf)
        data = b.getvalue()
        blocks.append(data[148:] if data[84:88] == b"DX10" else data[128:])
    w, h = levels[0].size
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000
    head = struct.pack("<4sIIIIIII", b"DDS ", 124, flags, h, w, len(blocks[0]), 0, len(blocks)) + b"\0" * 44
    head += struct.pack("<II4sIIIII", 32, 0x4, pf.encode(), 0, 0, 0, 0, 0)
    head += struct.pack("<IIIII", 0x1000 | 0x400008, 0, 0, 0, 0)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(head + b"".join(blocks))
    os.replace(tmp, path)
    return sum(len(b) for b in blocks)


def chain(img, plain):
    """Level 0 and every level below it to 1 x 1, each the box mean of the one above: an AG normal map's channel by
    channel (its alpha is the normal's x, not coverage), another's with Pillow's alpha-aware resize."""
    _, Image = imaging()
    out = [img]
    while out[-1].size != (1, 1):
        lv = out[-1]
        w, h = max(1, lv.width // 2), max(1, lv.height // 2)
        if plain:
            out.append(Image.merge("RGBA", [c.resize((w, h), Image.Resampling.BOX) for c in lv.split()]))
        else:
            out.append(lv.resize((w, h), Image.Resampling.BOX))
    return out


class Job:
    """One picture to make: the dumped texture's file, its kind, the size it is made at, and the files it writes."""

    def __init__(self, src, tid, w, h, fmt, kind, scale):
        self.src, self.id, self.w, self.h, self.fmt, self.kind = src, tid, w, h, fmt, kind
        self.tw, self.th = w * scale, h * scale
        self.pad = max(2, min(16, min(w, h) // 8))


def prepare(job, normals_by_upscaler):
    """The texels to upscale, padded: RGB for the upscaler (a normal map's normal as RGB when the upscaler is to take
    it), and what is kept apart."""
    np, Image = imaging()
    a = np.asarray(Image.open(job.src).convert("RGBA"))
    mode = "wrap" if tiles(a) else "reflect"
    p = job.pad
    padded = np.pad(a, ((p, p), (p, p), (0, 0)), mode=mode)
    if job.kind == "normal":
        x = padded[..., 3].astype(np.float32) / 127.5 - 1.0
        y = padded[..., 1].astype(np.float32) / 127.5 - 1.0
        z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
        xyz = np.stack([x, y, z], axis=-1)
        rgb = np.clip((xyz * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8) if normals_by_upscaler else None
        return {"rgb": rgb, "xyz": xyz}
    return {"rgb": padded[..., :3].copy(), "alpha": padded[..., 3].copy() if job.kind == "alpha" else None}


def finish(job, prep, up_rgb, fmt, out_dir, scale):
    """The upscaled texels cropped to the texture's own, a normal map normalised and packed back as AG, alpha upscaled
    apart, and written: a DDS with its chain, or a PNG. Returns (file, bytes on the GPU)."""
    np, Image = imaging()
    s, p = scale, job.pad
    W, H = (job.w + 2 * p) * s, (job.h + 2 * p) * s
    crop = (slice(p * s, p * s + job.th), slice(p * s, p * s + job.tw))
    if job.kind == "normal":
        if up_rgb is not None:
            if up_rgb.shape[1] != W or up_rgb.shape[0] != H:
                up_rgb = lanczos_rgb(up_rgb, W, H)
            n = up_rgb.astype(np.float32) / 127.5 - 1.0
        else:
            n = np.stack([resize_channel(prep["xyz"][..., c], W, H) for c in range(3)], axis=-1)
        n = n[crop]
        n[..., 2] = np.maximum(n[..., 2], 0.0)
        n /= np.maximum(np.sqrt((n * n).sum(axis=-1, keepdims=True)), 1e-6)
        out = np.empty(n.shape[:2] + (4,), np.uint8)
        out[..., 0] = 255
        out[..., 1] = np.clip((n[..., 1] * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        out[..., 2] = 0
        out[..., 3] = np.clip((n[..., 0] * 0.5 + 0.5) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    else:
        if up_rgb.shape[1] != W or up_rgb.shape[0] != H:
            up_rgb = lanczos_rgb(up_rgb, W, H)
        out = np.empty((job.th, job.tw, 4), np.uint8)
        out[..., :3] = up_rgb[crop]
        if prep.get("alpha") is not None:
            al = np.asarray(Image.fromarray(prep["alpha"], "L").resize((W, H), Image.Resampling.LANCZOS))
            out[..., 3] = al[crop]
        else:
            out[..., 3] = 255
    img = Image.fromarray(out, "RGBA")
    has_alpha = job.kind != "colour"
    if fmt == "dds" and job.tw % 4 == 0 and job.th % 4 == 0:
        path = os.path.join(out_dir, job.id + ".dds")
        return path, write_dds(path, chain(img, job.kind == "normal"), has_alpha)
    path = os.path.join(out_dir, job.id + ".png")
    img.save(path + ".part.png", compress_level=4)
    os.replace(path + ".part.png", path)
    return path, job.tw * job.th * 4 * 4 // 3


def lanczos_job(args):
    """One picture with the built-in upscaler (Lanczos), start to end: for a pool."""
    job, fmt, out_dir, scale = args
    prep = prepare(job, False)
    np, _ = imaging()
    up = None
    if job.kind != "normal":
        h, w = prep["rgb"].shape[:2]
        up = lanczos_rgb(prep["rgb"], w * scale, h * scale)
    return finish(job, prep, up, fmt, out_dir, scale)


def read_aliases(path):
    """aliases.txt's lines as (texture id, picture) pairs, and its text."""
    if not os.path.isfile(path):
        return {}, ""
    text = open(path, encoding="utf-8-sig").read()
    pairs = {}
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and not parts[0].startswith("#"):
            pairs[parts[0].lower()] = parts[1]
    return pairs, text


def cmd_upscale(args):
    np, Image = imaging()
    if not os.path.isdir(args.dump):
        raise ModError("no folder %s" % args.dump)
    if args.scale not in (2, 3, 4):
        raise ModError("--scale is 2, 3 or 4")
    if args.batch < 1:
        raise ModError("--batch is 1 or more")
    out_dir = os.path.join(args.mod, "textures")
    os.makedirs(out_dir, exist_ok=True)
    only = {i.strip().lower() for i in args.only.split(",")} if args.only else None

    # The dump, each texture's kind, and the ones that are one picture (the same texels): made once, the others
    # given it by aliases.txt.
    counts, groups, order = {}, {}, []
    for name in sorted(os.listdir(args.dump)):
        m = DUMP_NAME.match(name)
        if not m:
            continue
        tid, w, h, fmt = m.group(1).lower(), int(m.group(2)), int(m.group(3)), int(m.group(4), 16)
        if only is not None and tid not in only:
            continue
        a = np.asarray(Image.open(os.path.join(args.dump, name)).convert("RGBA"))
        if a.shape[1] != w or a.shape[0] != h:
            counts["left out: not the size its name says"] = counts.get("left out: not the size its name says", 0) + 1
            continue
        kind = texture_kind(a, fmt, w, h, args.min_side)
        if kind not in KINDS:
            counts[kind] = counts.get(kind, 0) + 1
            continue
        key = hashlib.sha1(a.tobytes() + struct.pack("<II", w, h)).hexdigest()
        if key not in groups:
            groups[key] = Job(os.path.join(args.dump, name), tid, w, h, fmt, kind, args.scale)
            groups[key].others = []
            order.append(key)
            counts[kind] = counts.get(kind, 0) + 1
        else:
            groups[key].others.append(tid)
            counts["the same as another"] = counts.get("the same as another", 0) + 1
    if args.limit:
        order = order[:args.limit]
    for k in sorted(counts):
        print("  %-48s %d" % (k, counts[k]))
    jobs = [groups[k] for k in order]
    todo = [j for j in jobs if args.force or not (os.path.isfile(os.path.join(out_dir, j.id + ".dds")) or
                                                   os.path.isfile(os.path.join(out_dir, j.id + ".png")))]
    print("%d pictures to make (%d already in %s), x%d, %s, by %s" % (
        len(todo), len(jobs) - len(todo), out_dir, args.scale, args.format,
        "Lanczos" if args.upscaler == "lanczos" else "the upscaler"))
    if args.dry_run:
        return 0

    import time
    t0 = time.time()
    made, gpu = 0, 0
    if args.upscaler == "lanczos":
        from multiprocessing import Pool
        with Pool(max(1, min(args.jobs, len(todo) or 1))) as pool:
            for path, b in pool.imap_unordered(lanczos_job, [(j, args.format, out_dir, args.scale) for j in todo],
                                               chunksize=4):
                made += 1
                gpu += b
                if made % 50 == 0:
                    print("  %d of %d" % (made, len(todo)))
    else:
        import shutil
        import tempfile
        batch = "{in_dir}" in args.upscaler
        with tempfile.TemporaryDirectory(prefix="upscale-") as tmp:
            # A few dozen at a time: the texels waiting for the upscaler, and its outputs, stay that many.
            for at in range(0, len(todo), args.batch):
                part = todo[at:at + args.batch]
                src_dir, dst_dir = os.path.join(tmp, "in"), os.path.join(tmp, "out")
                for d in (src_dir, dst_dir):
                    shutil.rmtree(d, ignore_errors=True)
                    os.makedirs(d)
                preps = {}
                for j in part:
                    by_up = j.kind != "normal" or args.normals == "upscaler"
                    preps[j.id] = prepare(j, by_up)
                    if by_up:
                        Image.fromarray(preps[j.id]["rgb"], "RGB").save(os.path.join(src_dir, j.id + ".png"))
                if batch and any(preps[j.id]["rgb"] is not None for j in part):
                    run_upscaler(args.upscaler, src_dir, dst_dir, args.scale)
                for j in part:
                    up = None
                    if preps[j.id]["rgb"] is not None:
                        src = os.path.join(src_dir, j.id + ".png")
                        dst = os.path.join(dst_dir, j.id + ".png")
                        if not batch:
                            run_upscaler(args.upscaler, src, dst, args.scale)
                        found = [f for f in os.listdir(dst_dir) if f.lower().startswith(j.id)]
                        if not found:
                            raise ModError("the upscaler wrote nothing for %s in %s" % (j.id, dst_dir))
                        with Image.open(os.path.join(dst_dir, found[0])) as im:
                            up = np.asarray(im.convert("RGB"))
                    path, b = finish(j, preps.pop(j.id), up, args.format, out_dir, args.scale)
                    made += 1
                    gpu += b
                    if made % 50 == 0:
                        print("  %d of %d" % (made, len(todo)))

    # The textures with the same texels as one made: aliases.txt, as `textures` would fold them.
    al_path = os.path.join(out_dir, "aliases.txt")
    have, text = read_aliases(al_path)
    add = ["%s %s" % (o, j.id) for j in jobs for o in j.others if o not in have]
    if add:
        with open(al_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text if text else "# <texture id> <the picture it takes: the id of one in this folder, or a file here>\n")
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write("\n".join(add) + "\n")
    ini = os.path.join(args.mod, "mod.ini")
    if not os.path.isfile(ini):
        with open(ini, "w", encoding="utf-8", newline="\n") as f:
            f.write("[mod]\nname = %s\ndescription = The game's textures at %dx, made from a dump of this PC's "
                    "game by modtools.py upscale.\n" % (os.path.basename(os.path.abspath(args.mod)), args.scale))
    print("%d pictures made in %.0f s, about %.0f MB on the GPU; %d more textures by aliases.txt" % (
        made, time.time() - t0, gpu / 1048576.0, len(add)))
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
    x = sub.add_parser("extract", help="every texture of the game's files, as the dump names them, without playing")
    x.add_argument("out", help="the folder to write them into (for upscale)")
    x.add_argument("--game", help="the game's PS3_GAME folder (default: the tree's vfs\\PS3_GAME)")
    x.add_argument("--updates", help="the game's updates' USRDIR (default: the tree's gamedata)")
    x.add_argument("--verbose", action="store_true", help="say each archive as it is read")
    u = sub.add_parser("upscale", help="a mod of the dumped textures made bigger, as DDS")
    u.add_argument("dump", help="the textures dump (textures-dump beside the settings)")
    u.add_argument("mod", help="the mod's folder to write (its textures\\ and mod.ini)")
    u.add_argument("--scale", type=int, default=2, help="2 (default), 3 or 4")
    u.add_argument("--upscaler", default="lanczos",
                   help='lanczos (built in, default), or a command: {in} {out} for one picture, {in_dir} {out_dir} '
                        'for a folder of them, {scale}')
    u.add_argument("--normals", choices=("lanczos", "upscaler"), default="lanczos",
                   help="normal maps by Lanczos (default) or by the upscaler, as their normals in RGB")
    u.add_argument("--format", choices=("dds", "png"), default="dds", help="dds (BC1/BC3 with the chain) or png")
    u.add_argument("--min-side", type=int, default=64, help="smaller textures are left out (default 64)")
    u.add_argument("--only", help="these texture ids alone, by commas")
    u.add_argument("--limit", type=int, default=0, help="the first n pictures alone (to try an upscaler)")
    u.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2),
                   help="pictures made at once with Lanczos (default half the CPU's threads)")
    u.add_argument("--batch", type=int, default=48, help="pictures handed to the upscaler at once (default 48)")
    u.add_argument("--force", action="store_true", help="make again pictures the mod has already")
    u.add_argument("--dry-run", action="store_true", help="say what it would make, write nothing")
    a = p.parse_args(argv)
    try:
        return {"patch": cmd_patch, "textures": cmd_textures, "upscale": cmd_upscale, "extract": cmd_extract}[a.cmd](a)
    except (ModError, OSError, gt.TextError) as e:
        print("modtools: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
