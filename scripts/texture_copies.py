"""The game's textures it keeps in more than one copy, for the textures layer (port/textures.cpp).

    texture_copies.py [--usrdir <a USRDIR> ...] [--out port/texture_copies.inc]

A texture of the game (an entry named TX<hash>.<hash>.dds in a .WAD or an .AS) can be in several archives, and not
always whole: an .AS holds a stub whose levels are in the .TS beside it, and a level's WAD often holds only the levels
a stream does not, from level 2 down, which the game draws with, as a texture of their own size, until the stream's
arrive (and in some of its cinematics, all along). Each copy reaches the GPU with an id of its own (XXH64 of its first
level, ps3recomp's libs/video/rsx_tex_replace.h), so a mod's picture for one would leave the others the game's.

This writes, for each texture with copies of more than one id, every copy's id and size, so the layer can give a
picture for one copy to all of them (scaled down for the smaller ones). DXT1/3/5 only: the game's other formats are
not kept in copies of different sizes. The base archives only: an update's .PATCH entries are not read.
Several releases' folders (--usrdir each) go into one table: the ids are of the textures' bytes, so a release
whose copy differs only adds ids to the texture's group.
"""
import argparse
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gametext as gt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FMT = {b"DXT1": 0x86, b"DXT3": 0x87, b"DXT5": 0x88}

# XXH64, as its specification has it (the ids are XXH64 of a texture's first level, the seed its format byte, width
# and height: format << 48 | width << 24 | height).
P1, P2, P3, P4, P5 = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63,
                      0x27D4EB2F165667C5)
M64 = (1 << 64) - 1


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & M64


def _round(acc, lane):
    acc = (acc + lane * P2) & M64
    return (_rotl(acc, 31) * P1) & M64


def xxh64(data, seed=0):
    n, p = len(data), 0
    if n >= 32:
        v1, v2, v3, v4 = (seed + P1 + P2) & M64, (seed + P2) & M64, seed & M64, (seed - P1) & M64
        lanes = struct.unpack_from("<%dQ" % (4 * (n // 32)), data, 0)
        for i in range(0, len(lanes), 4):
            v1 = _round(v1, lanes[i])
            v2 = _round(v2, lanes[i + 1])
            v3 = _round(v3, lanes[i + 2])
            v4 = _round(v4, lanes[i + 3])
        p = 32 * (n // 32)
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & M64
        for v in (v1, v2, v3, v4):
            h ^= _round(0, v)
            h = (h * P1 + P4) & M64
    else:
        h = (seed + P5) & M64
    h = (h + n) & M64
    while p + 8 <= n:
        h ^= _round(0, struct.unpack_from("<Q", data, p)[0])
        h = (_rotl(h, 27) * P1 + P4) & M64
        p += 8
    if p + 4 <= n:
        h ^= (struct.unpack_from("<I", data, p)[0] * P1) & M64
        h = (_rotl(h, 23) * P2 + P3) & M64
        p += 4
    while p < n:
        h ^= (data[p] * P5) & M64
        h = (_rotl(h, 11) * P1) & M64
        p += 1
    h ^= h >> 33
    h = (h * P2) & M64
    h ^= h >> 29
    h = (h * P3) & M64
    h ^= h >> 32
    return h


def tex_id(level, fmt, w, h):
    return xxh64(level, (fmt & 0xFF) << 48 | (w & 0xFFFFFF) << 24 | (h & 0xFFFFFF))


def entries(d):
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


def copies(d, ts):
    """(name, id, width, height) of each texture entry of a WAD-form file that has its first level here or in ts."""
    for name, fl, at, size in entries(d):
        if fl != 0x16 or size < 208 or not name.upper().startswith("TX"):
            continue
        b = d[at:at + size]
        off, nlev = struct.unpack_from(">II", b, 60)
        h, w = struct.unpack_from("<II", b, 80 + 12)
        fmt = FMT.get(bytes(b[80 + 84:80 + 88]))
        if not fmt or not w or not h or w > 8192 or h > 8192:
            continue
        bpb = 8 if fmt == 0x86 else 16
        k = first_level(w, h, bpb, size - 208)
        if k is not None:
            lw, lh = max(1, w >> k), max(1, h >> k)
            n = level_bytes(lw, lh, bpb)
            yield name, tex_id(b[208:208 + n], fmt, lw, lh), lw, lh
        elif ts is not None and off < 0xFFFFFFF0 and nlev <= 16 and off + level_bytes(w, h, bpb) <= len(ts):
            yield name, tex_id(ts[off:off + level_bytes(w, h, bpb)], fmt, w, h), w, h


def scan(usrdir, found, log=print):
    """Each texture's copies in a USRDIR's archives into found: name -> {id: (w, h)}."""
    arcs = sorted(os.path.join(dp, f) for dp, dn, fn in os.walk(usrdir) for f in fn
                  if f.upper().endswith(".PSARC") and not f.upper().startswith("TPPS"))
    t0 = time.time()
    for i, a in enumerate(arcs):
        try:
            names = gt.psarc_names(a)
        except (OSError, gt.TextError) as e:
            log("  %s: left out (%s)" % (os.path.basename(a), e))
            continue
        files = [n for n in names if n.upper().endswith((".AS", ".WAD"))]
        have = set(names)
        for n in files:
            d = gt.psarc_read(a, {n})[n]
            ts = None
            if n.upper().endswith(".AS") and n[:-3] + ".TS" in have:
                ts = gt.psarc_read(a, {n[:-3] + ".TS"})[n[:-3] + ".TS"]
            for name, tid, w, h in copies(d, ts):
                found.setdefault(name.upper(), {})[tid] = (w, h)
        log("  %d/%d %s: %d files, %.0f s" % (i + 1, len(arcs), os.path.basename(a), len(files), time.time() - t0))


def write_inc(found, path, what):
    groups = [(name, ids) for name, ids in sorted(found.items()) if len(ids) > 1]
    n = sum(len(ids) for _, ids in groups)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("/* Generated by scripts/texture_copies.py from %s. Do not edit.\n" % what)
        f.write(" * The textures the game keeps in more than one copy, each copy's id and size, copies of a texture together\n")
        f.write(" * (one group a texture, in the order of their names): %d textures, %d copies. */\n" % (len(groups), n))
        f.write("static const TexCopy k_tex_copies[] = {\n")
        if not groups:
            f.write("    { 0x0ULL, 0, 0, 0 },   /* none: an array has an entry */\n")
        for g, (name, ids) in enumerate(groups):
            for tid, (w, h) in sorted(ids.items(), key=lambda kv: (-kv[1][0] * kv[1][1], kv[0])):
                f.write("    { 0x%016xULL, %u, %u, %u },\n" % (tid, w, h, g))
        f.write("};\n")
    return len(groups), n


def release_of(usrdir):
    """The title id and version of a USRDIR's PARAM.SFO (beside it), or its folder's name."""
    sfo = os.path.join(os.path.dirname(os.path.normpath(usrdir)), "PARAM.SFO")
    try:
        d = open(sfo, "rb").read()
        kt, dt, n = struct.unpack_from("<III", d, 8)
        vals = {}
        for i in range(n):
            ko, fmt, ln, mx, do = struct.unpack_from("<HHIII", d, 20 + 16 * i)
            key = d[kt + ko:d.index(b"\0", kt + ko)].decode("latin-1")
            vals[key] = d[dt + do:dt + do + ln].split(b"\0")[0].decode("latin-1")
        if vals.get("TITLE_ID"):
            return "%s %s" % (vals["TITLE_ID"], vals.get("APP_VER", vals.get("VERSION", "")))
    except (OSError, ValueError, struct.error):
        pass
    return os.path.basename(os.path.dirname(os.path.normpath(usrdir)))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usrdir", action="append",
                    help="a release's USRDIR, as many as there are (default: vfs\\PS3_GAME\\USRDIR)")
    ap.add_argument("--out", default=os.path.join(ROOT, "port", "texture_copies.inc"))
    a = ap.parse_args(argv[1:])
    dirs = a.usrdir or [os.path.join(ROOT, "vfs", "PS3_GAME", "USRDIR")]
    found, what = {}, []
    for d in dirs:
        if not os.path.isdir(d):
            print("no folder %s" % d)
            return 2
        scan(d, found)
        what.append(release_of(d))
    g, n = write_inc(found, a.out, "%s's archives (%d textures in them)" % (" and ".join(what), len(found)))
    print("%s: %d textures with copies of more than one id, %d copies" % (a.out, g, n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
