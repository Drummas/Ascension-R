"""The TSS (PSN Title Small Storage) God of War: Ascension reads its online settings from, written from our own block
files (docs/notes/2026-11-22-multiplayer-phase0.md, phase1.md).

    mp_tss.py build <block folder> <out file> [--elf GOWA.elf]
    mp_tss.py dump <tss file> [--elf GOWA.elf]

The game asks PSN for its TSS with sceNpLookupTitleSmallStorageAsync (the port gives it the file PS3_NP_TSS_FILE
names), decrypts it in place (func_0035D684: Blowfish in OFB mode, its cipher library's algorithm 2 with option 4,
a 16-byte key and an 8-byte IV in the executable at 0x0083B928) and reads named blocks out of it:

    +0x00 u32 version, 2          +0x0C u32 block count
    +0x10 entries of 0x2C bytes:  char name[32]; u16 size; u16 offset (from +0); u32 stamp; u32 block version
    then the blocks: JSON text for jansson's json_loads, so each one ends in a NUL (counted in its size)

A reader asks for a block by name and version (func_0035DF34: MatchConfig 10, Playlist 7, ...) and gets it only
when an entry has that exact version, after VersionMap (version 1, {"Blocks": [{"Name": ..., "<app version>":
[[from, to], ...]}]}) has had its say. The stamp tells a reader whether a block changed since it last read it.

The key, the IV and Blowfish's tables are read from the player's own GOWA.elf (GOWA_ELF, else gamedata/GOWA.elf);
none of them is kept here. The block folder holds <Name>.json files; blocks.txt there lists "<Name> <version>" in
the order the file keeps them.
"""
import argparse
import json
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_EA = 0x0083B928            # 16-byte key, then the 8-byte IV
BF_P_EA = 0x00689CC0           # Blowfish's P-array, 18 words
BF_S_EA = 0x00858E40           # its four S-boxes, 256 words each
TSS_MAX = 0x10000              # the game's buffer
HEADER, ENTRY = 0x10, 0x2C


class Elf:
    def __init__(self, path):
        with open(path, "rb") as f:
            d = f.read()
        if d[:4] != b"\x7fELF":
            sys.exit("%s is not an ELF (GOWA.elf, the decrypted executable)" % path)
        phoff = struct.unpack(">Q", d[0x20:0x28])[0]
        phentsize, phnum = struct.unpack(">HH", d[0x36:0x3A])
        self.segs = []
        for i in range(phnum):
            o = phoff + i * phentsize
            p_type, _flags, p_offset, p_vaddr, _paddr, p_filesz = struct.unpack(">IIQQQQ", d[o:o + 40])
            if p_type == 1 and p_filesz:
                self.segs.append((p_vaddr, d[p_offset:p_offset + p_filesz]))

    def read(self, ea, n):
        for v, b in self.segs:
            if v <= ea and ea + n <= v + len(b):
                return b[ea - v:ea - v + n]
        sys.exit("0x%08X is not in the executable: not God of War: Ascension's GOWA.elf?" % ea)


class Blowfish:
    def __init__(self, key, p, s):
        self.p = list(p)
        self.s = [list(s[k * 256:(k + 1) * 256]) for k in range(4)]
        j = 0
        for i in range(18):
            w = 0
            for _ in range(4):
                w = ((w << 8) | key[j]) & 0xFFFFFFFF
                j = (j + 1) % len(key)
            self.p[i] ^= w
        left = right = 0
        for i in range(0, 18, 2):
            left, right = self.encrypt(left, right)
            self.p[i], self.p[i + 1] = left, right
        for box in self.s:
            for i in range(0, 256, 2):
                left, right = self.encrypt(left, right)
                box[i], box[i + 1] = left, right

    def f(self, x):
        s = self.s
        return ((((s[0][x >> 24] + s[1][(x >> 16) & 0xFF]) & 0xFFFFFFFF) ^ s[2][(x >> 8) & 0xFF]) + s[3][x & 0xFF]) \
            & 0xFFFFFFFF

    def encrypt(self, left, right):
        for i in range(16):
            left ^= self.p[i]
            right ^= self.f(left)
            left, right = right, left
        left, right = right, left
        return left ^ self.p[17], right ^ self.p[16]

    def decrypt(self, left, right):
        for i in range(17, 1, -1):
            left ^= self.p[i]
            right ^= self.f(left)
            left, right = right, left
        left, right = right, left
        return left ^ self.p[0], right ^ self.p[1]


def cipher(elf):
    p = struct.unpack(">18I", elf.read(BF_P_EA, 72))
    s = struct.unpack(">1024I", elf.read(BF_S_EA, 4096))
    if p[0] != 0x243F6A88 or s[0] != 0xD1310BA6 or s[256] != 0x4B7A70E9:
        sys.exit("Blowfish's tables are not where they should be: another build of the game?")
    probe = Blowfish(bytes(8), p, s)
    if probe.encrypt(0, 0) != (0x4EF99745, 0x6198DD78):    # the published test vector: key 0, block 0
        sys.exit("Blowfish self-test failed")
    kv = elf.read(KEY_EA, 24)
    return Blowfish(kv[:16], p, s), kv[16:24]


def blocks_of(data):
    return [struct.unpack(">2I", data[i:i + 8]) for i in range(0, len(data), 8)]


def crypt(bf, iv, data, mode, decrypt):
    if len(data) % 8:
        data += bytes(8 - len(data) % 8)
    out = bytearray()
    prev = struct.unpack(">2I", iv)
    for left, right in blocks_of(data):
        if mode == "cbc":
            if decrypt:
                pl, pr = bf.decrypt(left, right)
                out += struct.pack(">2I", pl ^ prev[0], pr ^ prev[1])
                prev = (left, right)
            else:
                prev = bf.encrypt(left ^ prev[0], right ^ prev[1])
                out += struct.pack(">2I", *prev)
        elif mode == "ecb":
            out += struct.pack(">2I", *(bf.decrypt if decrypt else bf.encrypt)(left, right))
        elif mode in ("cfb", "ofb"):
            ks = bf.encrypt(*prev)
            c = (left ^ ks[0], right ^ ks[1])
            out += struct.pack(">2I", *c)
            prev = ks if mode == "ofb" else ((left, right) if decrypt else c)
        else:
            sys.exit("mode %s?" % mode)
    return bytes(out)


def pack(blocks):
    """blocks: [(name, version, text bytes)] -> the plaintext TSS."""
    off = HEADER + ENTRY * len(blocks)
    table, body = bytearray(), bytearray()
    for name, version, text in blocks:
        data = text + b"\0"
        if len(name) >= 32:
            sys.exit("block name too long: %s" % name)
        table += name.encode("ascii").ljust(32, b"\0")
        table += struct.pack(">HHII", len(data), off, zlib.crc32(data) | 1, version)
        body += data
        off += len(data)
    out = struct.pack(">4I", 2, 0, 0, len(blocks)) + table + body
    if len(out) > TSS_MAX - 8:
        sys.exit("the TSS is %d bytes; the game's buffer holds %d" % (len(out), TSS_MAX))
    return out


def unpack(plain):
    version, _a, _b, count = struct.unpack(">4I", plain[:16])
    rows = []
    for i in range(count):
        e = plain[HEADER + ENTRY * i:HEADER + ENTRY * (i + 1)]
        name = e[:32].split(b"\0")[0].decode("ascii", "replace")
        size, off, stamp, bver = struct.unpack(">HHII", e[32:44])
        rows.append((name, bver, size, off, stamp, plain[off:off + size]))
    return version, rows


def read_folder(folder):
    order = []
    with open(os.path.join(folder, "blocks.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line:
                name, version = line.split()
                order.append((name, int(version)))
    out = []
    for name, version in order:
        with open(os.path.join(folder, name + ".json"), "rb") as f:
            text = f.read().strip()
        out.append((name, version, text))
    return out


def with_server(blocks, host, sam_port=None, geo_port=None):
    """The blocks with MatchConfig pointing the game's matchmaker (every target) and geo lookups at host."""
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("SAMServerHostAddr", "GeoServerAddr"):
                    o[k] = host
                elif k == "SAMServerPort" and sam_port:
                    o[k] = sam_port
                elif k == "GeoPort" and geo_port:
                    o[k] = geo_port
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    out = []
    for name, version, text in blocks:
        if name == "MatchConfig":
            doc = json.loads(text)
            walk(doc)
            text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
        out.append((name, version, text))
    return out


def main(argv):
    ap = argparse.ArgumentParser(description="God of War: Ascension's TSS: build from block files, or dump one.")
    ap.add_argument("cmd", choices=("build", "dump"))
    ap.add_argument("src")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--elf", default=os.environ.get("GOWA_ELF") or os.path.join(ROOT, "gamedata", "GOWA.elf"))
    ap.add_argument("--mode", default="ofb", choices=("ofb", "cbc", "ecb", "cfb"))
    ap.add_argument("--server", help="build: the matchmaker's (and geo's) address instead of the blocks' own")
    ap.add_argument("--sam-port", type=int, help="build, with --server: the matchmaker's port")
    ap.add_argument("--geo-port", type=int, help="build, with --server: the geo port")
    a = ap.parse_args(argv)
    bf, iv = cipher(Elf(a.elf))
    if a.cmd == "build":
        if not a.out:
            ap.error("build needs an output file")
        blocks = read_folder(a.src)
        if a.server:
            blocks = with_server(blocks, a.server, a.sam_port, a.geo_port)
        plain = pack(blocks)
        enc = crypt(bf, iv, plain, a.mode, False)
        with open(a.out, "wb") as f:
            f.write(enc)
        print("%s: %d blocks, %d bytes (%s)" % (a.out, len(blocks), len(enc), ", ".join("%s %d" % (n, v) for n, v, _ in blocks)))
    else:
        plain = crypt(bf, iv, open(a.src, "rb").read(), a.mode, True)
        version, rows = unpack(plain)
        print("version %d, %d blocks" % (version, len(rows)))
        for name, bver, size, off, stamp, data in rows:
            print("  %-20s v%-3d %5d bytes at 0x%04X stamp %08X  %s" % (name, bver, size, off, stamp,
                                                                     data[:60].decode("utf-8", "replace").replace("\n", " ")))


if __name__ == "__main__":
    main(sys.argv[1:])
