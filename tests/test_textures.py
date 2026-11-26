#!/usr/bin/env python3
"""Texture mods: ps3recomp's libs/video/rsx_tex_replace.c (the ids, the decode, the chain) and port/textures.cpp
(the pictures of the mods that are on, an overlay over the game's own, the dump, the optional Xbox button icons mod
that comes with the port).

Builds ps3recomp's tests/test_rsx_tex_replace.c, and a driver of port/textures.cpp with port/mods.cpp, both with
clang-cl; the pictures are PNGs this test writes. No game file is used.

Usage:
    python tests/test_textures.py
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS3 = ROOT / "ps3recomp"

DRIVER = r'''
#include "mods.h"
#include "textures.h"
#include "rsx_tex_replace.h"
#include "ps3emu/ps3_settings.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
/* t.exe <ini> <dump dir or -> <command>...: has <id>; picture <id> <w> <h> <r,g,b,a of the base> (a picture read
 * later waited for, as the backend does: ready(), then asked again); first <id> <w> <h> <r,g,b,a>: the first answer
 * alone; dump <id> <w> <h> <r,g,b,a> */
static void parse4(const char* s, unsigned char* px)
{
    unsigned a, b, c, d;
    sscanf(s, "%u,%u,%u,%u", &a, &b, &c, &d);
    px[0] = (unsigned char)a; px[1] = (unsigned char)b; px[2] = (unsigned char)c; px[3] = (unsigned char)d;
}
int main(int argc, char** argv)
{
    ps3_settings_load(argv[1]);
    ModList l;
    mods_scan(&l, 1);
    wchar_t dump[1024] = L"";
    if (strcmp(argv[2], "-")) MultiByteToWideChar(CP_UTF8, 0, argv[2], -1, dump, 1024);
    printf("textures %d\n", gowa_textures_start(l, dump));
    const rsx_tex_hooks* hk = rsx_tex_get_hooks();
    if (!hk) { printf("hooks none\n"); return 0; }
    for (int a = 3; a < argc; a++) {
        if (!strcmp(argv[a], "has")) {
            const u64 id = _strtoui64(argv[++a], NULL, 16);
            printf("has %016llx %d\n", (unsigned long long)id, hk->has ? hk->has(id) : -1);
        } else if (!strcmp(argv[a], "picture") || !strcmp(argv[a], "first") || !strcmp(argv[a], "dump")) {
            const int pic = strcmp(argv[a], "dump") != 0, wait = !strcmp(argv[a], "picture");
            const u64 id = _strtoui64(argv[++a], NULL, 16);
            const u32 w = (u32)atoi(argv[++a]), h = (u32)atoi(argv[++a]);
            unsigned char px[4];
            parse4(argv[++a], px);
            unsigned char* base = (unsigned char*)malloc((size_t)w * h * 4);
            for (size_t i = 0; i < (size_t)w * h; i++) memcpy(base + i * 4, px, 4);
            if (pic) {
                rsx_tex_picture out;
                memset(&out, 0, sizeof out);
                int got = hk->picture(id, w, h, hk->has(id) == 2 ? base : NULL, &out);
                for (int t = 0; wait && got == RSX_TEXPIC_LATER && t < 1000; t++) {
                    Sleep(5);
                    if (hk->ready && hk->ready(id)) {
                        memset(&out, 0, sizeof out);
                        got = hk->picture(id, w, h, hk->has(id) == 2 ? base : NULL, &out);
                    }
                }
                printf("picture %d %ux%u", got, out.w, out.h);
                if (got == 1 && out.form)   /* its own blocks and chain */
                    printf(" form %u levels %u bytes %llu", out.form, out.levels, (unsigned long long)out.data_bytes);
                else if (got == 1)   /* the four corners and the middle */
                    for (int k = 0; k < 5; k++) {
                        const u32 x = k == 4 ? out.w / 2 : (k & 1) ? out.w - 1 : 0, y = k == 4 ? out.h / 2 : (k & 2) ? out.h - 1 : 0;
                        const unsigned char* p = out.rgba + ((size_t)y * out.w + x) * 4;
                        printf(" %u,%u,%u,%u", p[0], p[1], p[2], p[3]);
                    }
                if (got == 1 && (out.flags & RSX_TEXPIC_PLAIN_CHAIN)) printf(" plain");
                printf("\n");
            } else if (hk->dump) {
                hk->dump(id, w, h, 0x88, base);
                hk->dump(id, w, h, 0x88, base);   /* once a run */
                Sleep(500);   /* the dump's own thread writes it */
                printf("dumped\n");
            }
            free(base);
        }
    }
    return 0;
}
'''


def png(path, w, h, px):
    """A PNG of w x h, RGBA8, every texel px(x, y)."""
    raw = b"".join(b"\0" + b"".join(bytes(px(x, y)) for x in range(w)) for y in range(h))
    def chunk(t, c): return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c) & 0xFFFFFFFF)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
                           chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def dds(path, w, h, form, levels, dx10=False):
    """A DDS of w x h, BC1 ('DXT1'), BC3 ('DXT5') or BC7 (DX10, DXGI 98), with levels levels of blocks (bytes k % 251
    in level k... the contents do not matter here)."""
    block = 8 if form == "BC1" else 16
    data = b""
    lw, lh = w, h
    for k in range(levels):
        data += bytes([k % 251]) * (max(1, (lw + 3) // 4) * max(1, (lh + 3) // 4) * block)
        lw, lh = max(1, lw // 2), max(1, lh // 2)
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | (0x20000 if levels > 1 else 0)
    cc = b"DX10" if dx10 or form == "BC7" else {"BC1": b"DXT1", "BC3": b"DXT5"}[form]
    head = struct.pack("<4sIIIIIII", b"DDS ", 124, flags, h, w, 0, 0, levels) + b"\0" * 44
    head += struct.pack("<II4sIIIII", 32, 0x4, cc, 0, 0, 0, 0, 0)
    head += struct.pack("<IIIII", 0x1000 | (0x400008 if levels > 1 else 0), 0, 0, 0, 0)
    if cc == b"DX10":
        head += struct.pack("<IIIII", {"BC1": 71, "BC3": 77, "BC7": 98}[form], 3, 0, 1, 0)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(head + data)
    return len(data)


def toolchain():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gowa
    env = gowa.toolchain_env()
    clang = shutil.which("clang-cl", path=env.get("PATH"))
    if not clang:
        if os.environ.get("CI"):
            raise AssertionError("no clang-cl")
        raise unittest.SkipTest("no clang-cl")
    return clang, env


class TexReplace(unittest.TestCase):
    """ps3recomp's tests/test_rsx_tex_replace.c."""

    def test_the_ids_the_decode_and_the_chain(self):
        clang, env = toolchain()
        with tempfile.TemporaryDirectory(prefix="tex-replace-") as d:
            exe = os.path.join(d, "t.exe")
            r = subprocess.run([clang, "/nologo", "/O1", "-D_CRT_SECURE_NO_WARNINGS", "/I" + str(PS3 / "include"),
                                "/I" + str(PS3 / "libs" / "video"), str(PS3 / "tests" / "test_rsx_tex_replace.c"),
                                str(PS3 / "libs" / "video" / "rsx_tex_replace.c"),
                                str(PS3 / "libs" / "video" / "rsx_texture_layout.c"), "/Fe" + exe, "/Fo" + d + "\\"],
                               capture_output=True, text=True, env=env, cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run([exe], capture_output=True, text=True, cwd=d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("rsx_tex_replace: ok", r.stdout)


class Textures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clang, env = toolchain()
        cls.tmp = tempfile.mkdtemp(prefix="textures-")
        cls.exe = os.path.join(cls.tmp, "t.exe")
        src = os.path.join(cls.tmp, "t.cpp")
        Path(src).write_text(DRIVER)
        z = ROOT / "third_party" / "zlib"
        cmd = [clang, "/nologo", "/O1", "/EHsc", "/std:c++17", "-D_CRT_SECURE_NO_WARNINGS", "/I" + str(ROOT / "port"),
               "/I" + str(ROOT), "/I" + str(PS3 / "include"), "/I" + str(PS3 / "libs" / "video"), src,
               str(ROOT / "port" / "textures.cpp"), str(ROOT / "port" / "mods.cpp"),
               str(PS3 / "runtime" / "settings" / "ps3_settings.c"), str(PS3 / "libs" / "video" / "rsx_tex_replace.c"),
               str(PS3 / "libs" / "video" / "rsx_texture_layout.c"),
               *[str(z / f) for f in ("adler32.c", "crc32.c", "inffast.c", "inflate.c", "inftrees.c", "zutil.c")],
               "/Fe" + cls.exe, "/Fo" + cls.tmp + "\\"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cls.tmp)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="m-", dir=self.tmp)
        self.mods = os.path.join(self.d, "mods")
        os.makedirs(self.mods)
        self.ini = os.path.join(self.d, "ascension-r.ini")
        Path(self.ini).write_text("[mods]\nfolder = %s\n" % self.mods)

    def run_t(self, dump="-", *a):
        r = subprocess.run([self.exe, self.ini, dump, *a], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return [ln for ln in r.stdout.splitlines() if not ln.startswith("[")]   # not the log's lines

    def test_a_picture_in_the_place_of_one_and_over_another(self):
        # A: a whole picture for one id, 8 x 4 red; and an overlay for another, a mod below having one for it too.
        png(os.path.join(self.mods, "A", "textures", "00000000000000aa.png"), 8, 4, lambda x, y: (255, 0, 0, 255))
        png(os.path.join(self.mods, "A", "textures", "sub", "00000000000000BB_64x64_88.overlay.png"), 4, 4,
            lambda x, y: (0, 0, 255, 255) if x == 0 else (0, 255, 0, 128) if x == 1 else (9, 9, 9, 1) if x == 2
            else (0, 0, 0, 0))
        png(os.path.join(self.mods, "B", "textures", "00000000000000bb.png"), 2, 2, lambda x, y: (1, 2, 3, 255))
        png(os.path.join(self.mods, "B", "textures", "not-an-id.png"), 2, 2, lambda x, y: (1, 2, 3, 255))
        Path(self.mods, "B", "textures", "00000000000000cc.png").write_bytes(b"not a png")
        out = self.run_t("-", "has", "aa", "has", "bb", "has", "cc", "has", "dd",
                         "picture", "aa", "2", "2", "0,0,0,0",
                         "picture", "bb", "2", "2", "100,100,100,200",
                         "picture", "cc", "2", "2", "0,0,0,0", "has", "cc")
        self.assertEqual(out[0], "textures 3")
        self.assertEqual(out[1:5], ["has 00000000000000aa 1", "has 00000000000000bb 2", "has 00000000000000cc 1",
                                    "has 00000000000000dd 0"])
        self.assertEqual(out[5], "picture 1 8x4 255,0,0,255 255,0,0,255 255,0,0,255 255,0,0,255 255,0,0,255")
        # Over the base (100,100,100,200), scaled to 4 x 4: column 0 the overlay's blue, column 3 the base, row 0
        # and 3 alike; the middle (2, 2), alpha 1: clear.
        self.assertEqual(out[6], "picture 1 4x4 0,0,255,255 100,100,100,200 0,0,255,255 100,100,100,200 0,0,0,0")
        # A file that is no picture: not taken, and not asked again.
        self.assertEqual(out[7:], ["picture 0 0x0", "has 00000000000000cc 0"])

    def test_a_picture_for_the_other_copies_of_its_texture(self):
        # port/texture_copies.inc: a texture with a whole copy and one of its level 2 (a quarter of each side).
        groups = {}
        for m in re.finditer(r"\{ 0x([0-9a-f]{16})ULL, (\d+), (\d+), (\d+) \}", (ROOT / "port" / "texture_copies.inc").read_text()):
            groups.setdefault(int(m.group(4)), []).append((m.group(1), int(m.group(2)), int(m.group(3))))
        pick = next(((a, b) for g in groups.values() for a in g for b in g
                     if b[1] * 4 == a[1] and b[2] * 4 == a[2]), None)
        if not pick:
            self.skipTest("no texture with a level 2 copy in port/texture_copies.inc")
        (big, bw, bh), (small, sw, sh) = pick
        # A picture of 16 x 16 for the whole copy, its left half red, its right half blue.
        png(os.path.join(self.mods, "A", "textures", big + ".png"), 16, 16,
            lambda x, y: (255, 0, 0, 255) if x < 8 else (0, 0, 255, 255))
        out = self.run_t("-", "has", big, "has", small, "picture", small, str(sw), str(sh), "0,0,0,0",
                         "picture", big, str(bw), str(bh), "0,0,0,0")
        self.assertEqual(out[0], "textures 2")
        self.assertEqual(out[1:3], ["has %s 1" % big, "has %s 1" % small])
        # The copy a quarter of the size: the picture a quarter too, 4 x 4, the halves kept.
        self.assertEqual(out[3], "picture 1 4x4 255,0,0,255 0,0,255,255 255,0,0,255 0,0,255,255 0,0,255,255")
        self.assertEqual(out[4], "picture 1 16x16 255,0,0,255 0,0,255,255 255,0,0,255 0,0,255,255 0,0,255,255")
        # A copy with a picture of its own keeps it; the picture of the small one goes to the big one as it is.
        os.remove(os.path.join(self.mods, "A", "textures", big + ".png"))
        png(os.path.join(self.mods, "A", "textures", small + "_mine.png"), 2, 2, lambda x, y: (7, 7, 7, 255))
        out = self.run_t("-", "picture", big, str(bw), str(bh), "0,0,0,0")
        self.assertEqual(out[0], "textures 2")
        self.assertEqual(out[1], "picture 1 2x2 7,7,7,255 7,7,7,255 7,7,7,255 7,7,7,255 7,7,7,255")
        png(os.path.join(self.mods, "A", "textures", big + ".png"), 4, 4, lambda x, y: (9, 9, 9, 255))
        out = self.run_t("-", "picture", small, str(sw), str(sh), "0,0,0,0")
        self.assertEqual(out[0], "textures 2")
        self.assertEqual(out[1], "picture 1 2x2 7,7,7,255 7,7,7,255 7,7,7,255 7,7,7,255 7,7,7,255")
        # A DDS for the whole copy, 32 x 32 with its chain: the copy a quarter of the size takes its chain from the
        # level of its size, 8 x 8; the whole one all of it.
        for f in os.listdir(os.path.join(self.mods, "A", "textures")):
            os.remove(os.path.join(self.mods, "A", "textures", f))
        n = dds(os.path.join(self.mods, "A", "textures", big + ".dds"), 32, 32, "BC1", 6)
        out = self.run_t("-", "picture", small, str(sw), str(sh), "0,0,0,0", "picture", big, str(bw), str(bh), "0,0,0,0")
        self.assertEqual(out[1], "picture 1 8x8 form 1 levels 4 bytes %d" % (32 + 8 + 8 + 8))
        self.assertEqual(out[2], "picture 1 32x32 form 1 levels 6 bytes %d" % n)

    def test_aliases_give_a_picture_to_more_textures(self):
        # A: a picture by its id and one by any name; aliases.txt gives them to more textures.
        png(os.path.join(self.mods, "A", "textures", "00000000000000aa.png"), 2, 2, lambda x, y: (10, 20, 30, 255))
        png(os.path.join(self.mods, "A", "textures", "atlas", "body.png"), 2, 2, lambda x, y: (40, 50, 60, 255))
        Path(self.mods, "A", "textures", "aliases.txt").write_text(
            "﻿# the id, then the picture\n"
            "00000000000000a1 00000000000000aa\n"
            "00000000000000a2   atlas/body.png\r\n"
            "00000000000000AA atlas/body.png\n"        # the folder has a picture of aa: that one
            "00000000000000a3 00000000000000ff\n"      # no picture of ff in the folder
            "00000000000000a4 ../outside.png\n"        # outside the folder
            "zz 00000000000000aa\n", encoding="utf-8")
        # B, below: its own picture of a1 loses to A's alias; its own alias is taken.
        png(os.path.join(self.mods, "B", "textures", "00000000000000a1.png"), 2, 2, lambda x, y: (1, 1, 1, 255))
        png(os.path.join(self.mods, "B", "textures", "00000000000000bb.png"), 2, 2, lambda x, y: (2, 2, 2, 255))
        Path(self.mods, "B", "textures", "aliases.txt").write_text("00000000000000b1 00000000000000bb\n")
        Path(self.ini).write_text("[mods]\nfolder = %s\norder = A|B\n" % self.mods)
        r = subprocess.run([self.exe, self.ini, "-", "has", "a1", "has", "a2", "has", "a3", "has", "a4", "has",
                            "b1", "picture", "a1", "2", "2", "0,0,0,0", "picture", "a2", "2", "2", "0,0,0,0",
                            "picture", "aa", "2", "2", "0,0,0,0", "picture", "b1", "2", "2", "0,0,0,0"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = [ln for ln in r.stdout.splitlines() if ln.startswith("[tex]")]
        out = [ln for ln in r.stdout.splitlines() if not ln.startswith("[")]
        self.assertIn("[tex] A: aliases.txt: 3 lines not taken; line 5: no picture of 00000000000000ff in the folder", log)
        self.assertTrue(any(ln.startswith("[tex] 3 pictures of mods (3 more textures by aliases.txt), for 5 textures")
                            for ln in log), log)
        self.assertEqual(out[0], "textures 5")   # aa, a1, a2; bb, b1
        self.assertEqual(out[1:6], ["has 00000000000000a1 1", "has 00000000000000a2 1", "has 00000000000000a3 0",
                                    "has 00000000000000a4 0", "has 00000000000000b1 1"])
        self.assertEqual(out[6], "picture 1 2x2 " + " ".join(["10,20,30,255"] * 5))
        self.assertEqual(out[7], "picture 1 2x2 " + " ".join(["40,50,60,255"] * 5))
        self.assertEqual(out[8], "picture 1 2x2 " + " ".join(["10,20,30,255"] * 5))
        self.assertEqual(out[9], "picture 1 2x2 " + " ".join(["2,2,2,255"] * 5))

    def test_dds_pictures_their_own_blocks_and_chain(self):
        # BC1 with its chain, BC7 by DX10's header, one not whole blocks wide, and a DDS beside a PNG of one id.
        n1 = dds(os.path.join(self.mods, "A", "textures", "00000000000000a1.dds"), 8, 8, "BC1", 4)
        n7 = dds(os.path.join(self.mods, "A", "textures", "00000000000000a7_upscaled.dds"), 16, 4, "BC7", 5)
        dds(os.path.join(self.mods, "A", "textures", "00000000000000a6.dds"), 6, 6, "BC1", 1)
        png(os.path.join(self.mods, "A", "textures", "00000000000000a3.png"), 2, 2, lambda x, y: (1, 1, 1, 255))
        n3 = dds(os.path.join(self.mods, "A", "textures", "00000000000000a3.dds"), 4, 4, "BC3", 3)
        r = subprocess.run([self.exe, self.ini, "-", "picture", "a1", "4", "4", "0,0,0,0",
                            "picture", "a7", "4", "4", "0,0,0,0", "picture", "a6", "4", "4", "0,0,0,0",
                            "picture", "a3", "4", "4", "0,0,0,0"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = [ln for ln in r.stdout.splitlines() if not ln.startswith("[")]
        log = [ln for ln in r.stdout.splitlines() + r.stderr.splitlines() if ln.startswith("[tex]")]
        self.assertEqual(n1, 32 + 8 + 8 + 8)
        self.assertEqual(out[1:], ["picture 1 8x8 form 1 levels 4 bytes %d" % n1,
                                   "picture 1 16x4 form 7 levels 5 bytes %d" % n7,
                                   "picture 0 0x0",
                                   "picture 1 4x4 form 3 levels 3 bytes %d" % n3])
        self.assertTrue(any("00000000000000a6.dds: not a multiple of 4 wide and high" in ln for ln in log), log)
        self.assertTrue(any("of the pictures are DDS" in ln for ln in log), log)
        self.assertTrue(any("MB on the GPU" in ln for ln in log), log)

    def test_pictures_are_read_ahead(self):
        # The first answer is "later" (-1): the game's own texture until the loader has read the picture; then the
        # picture. GOWA_PICTURE_ASYNC=0 reads it when asked.
        png(os.path.join(self.mods, "A", "textures", "00000000000000aa.png"), 8, 4, lambda x, y: (255, 0, 0, 255))
        out = self.run_t("-", "first", "aa", "8", "4", "0,0,0,0", "picture", "aa", "8", "4", "0,0,0,0")
        self.assertEqual(out[1], "picture -1 0x0")
        self.assertEqual(out[2], "picture 1 8x4 " + " ".join(["255,0,0,255"] * 5))
        env = dict(os.environ, GOWA_PICTURE_ASYNC="0")
        r = subprocess.run([self.exe, self.ini, "-", "first", "aa", "8", "4", "0,0,0,0"], capture_output=True,
                           text=True, env=env)
        self.assertIn("picture 1 8x4 " + " ".join(["255,0,0,255"] * 5), r.stdout)

    def test_an_ag_normal_maps_chain_is_plain(self):
        # Red full, blue none, the normal's y in green and its x in alpha, both spread: the chain without alpha's
        # weight. A colour picture with alpha keeps it.
        png(os.path.join(self.mods, "A", "textures", "00000000000000ab.png"), 16, 16,
            lambda x, y: (255, 60 + x * 8, 0, 40 + y * 10))
        png(os.path.join(self.mods, "A", "textures", "00000000000000ac.png"), 16, 16,
            lambda x, y: (90, 60 + x * 8, 200, 40 + y * 10))
        out = self.run_t("-", "picture", "ab", "16", "16", "0,0,0,0", "picture", "ac", "16", "16", "0,0,0,0")
        self.assertTrue(out[1].endswith(" plain"), out[1])
        self.assertFalse(out[2].endswith(" plain"), out[2])

    def test_the_dump(self):
        dump = os.path.join(self.d, "dump")
        out = self.run_t(dump, "dump", "0123456789abcdef", "3", "2", "10,20,30,40")
        self.assertEqual(out[0], "textures 0")
        self.assertEqual(os.listdir(dump), ["0123456789abcdef_3x2_88.png"])
        data = Path(dump, "0123456789abcdef_3x2_88.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (3, 2))
        # Nothing at all: no hooks.
        self.assertEqual(self.run_t("-"), ["textures 0", "hooks none"])

    def test_the_optional_xbox_button_icons(self):
        # The game's buttons: Cross, Circle, Square, Triangle and Select's bar. None has a picture until the mod that
        # comes with the port is in the folder.
        ids = ("d8c17e20cbbe71ac", "1f52688dc50e2bfb", "2133aab0625680af", "660940394f9aee54", "a4f295497b5454b7")
        has = [w for i in ids for w in ("has", i)]
        self.assertEqual(self.run_t("-", *has), ["textures 0", "hooks none"])
        shutil.copytree(ROOT / "optional-mods" / "Xbox button icons", os.path.join(self.mods, "Xbox button icons"))
        out = self.run_t("-", *has, "picture", ids[0], "64", "64", "0,0,0,0", "picture", ids[4], "64", "32", "0,0,0,0")
        self.assertEqual(out[0], "textures 5")
        self.assertEqual(out[1:6], ["has %s 1" % i for i in ids])
        self.assertTrue(out[6].startswith("picture 1 128x128 "), out[6])
        self.assertTrue(out[7].startswith("picture 1 128x64 "), out[7])
        # A mod above it with a picture of a button: that one.
        png(os.path.join(self.mods, "Mine", "textures", "d8c17e20cbbe71ac.png"), 2, 2, lambda x, y: (5, 5, 5, 255))
        Path(self.ini).write_text("[mods]\nfolder = %s\norder = Mine|Xbox button icons\n" % self.mods)
        out = self.run_t("-", "picture", ids[0], "64", "64", "0,0,0,0")
        self.assertEqual(out[1], "picture 1 2x2 5,5,5,255 5,5,5,255 5,5,5,255 5,5,5,255 5,5,5,255")
        # Switched off in the Mods tab: the game's own again.
        Path(self.ini).write_text("[mods]\nfolder = %s\noff = Xbox button icons|Mine\n" % self.mods)
        self.assertEqual(self.run_t("-", *has), ["textures 0", "hooks none"])


if __name__ == "__main__":
    unittest.main()
