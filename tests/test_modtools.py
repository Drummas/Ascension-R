#!/usr/bin/env python3
"""scripts/modtools.py: a .PATCH in the game's form made and put over its file again, the game's own file found in
its updates before its disc, the patch command on a made-up game folder, and pictures that are one file folded into
aliases.txt. No game file is used.

Usage:
    python tests/test_modtools.py
"""
import os
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gametext as gt  # noqa: E402
import modtools as mt  # noqa: E402


def noise(n, seed):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


def steps_of(patch):
    n = struct.unpack(">H", patch[2:4])[0]
    return [struct.unpack(">II", patch[4 + 8 * i:12 + 8 * i]) for i in range(n)]


class Patches(unittest.TestCase):
    def test_a_patch_gives_the_file_back(self):
        base = noise(300000, 1)
        t = bytearray(base)
        t[1000:1010] = b"X" * 10            # a little in place
        t[50000:70000] = bytes(20000)       # more in place
        t += b"tail" * 5000                 # added at the end
        t = bytes(t)
        p = mt.make_patch(base, t)
        self.assertEqual(mt.apply_patch(base, p), t)
        self.assertEqual(struct.unpack(">H", p[:2])[0], 4)
        n, from_base, own = mt.patch_summary(p)
        self.assertEqual(from_base + own, len(t))
        # In place: a piece of 64 for the ten bytes, the 20000 in pieces of 64 (it starts and ends on one), the tail.
        self.assertEqual(own, 64 + 20032 + 20000)
        # The patch's own steps take its data in order, one after the other.
        at = 0
        for frm, size in steps_of(p):
            if frm & mt.OWN:
                self.assertEqual(frm & ~mt.OWN, at)
                at += size
        self.assertEqual(len(p), 4 + 8 * n + at)

    def test_shorter_the_same_and_empty(self):
        base = noise(100000, 2)
        for t in (base[:30000], base, b"", base + base[:5000]):
            p = mt.make_patch(base, t)
            self.assertEqual(mt.apply_patch(base, p), t)
        self.assertEqual(steps_of(mt.make_patch(base, base)), [(0, 100000)])
        # A short stretch in common between two of the patch's own goes in with them: one step, not three.
        t = bytearray(base[:4096])
        t[0:64] = b"A" * 64
        t[80:144] = b"B" * 64   # 64..80 the same, but that piece of 64 differs (80..128)
        p = mt.make_patch(base[:4096], bytes(t))
        self.assertEqual(mt.apply_patch(base[:4096], p), bytes(t))

    def test_too_many_places_takes_bigger_pieces(self):
        base = noise(1 << 22, 3)
        t = bytearray(base)
        for i in range(0, len(t), 128):   # every other piece of 64 differs: 65536 own steps and as many copies
            t[i] = t[i] ^ 0xFF
        t = bytes(t)
        p = mt.make_patch(base, t)
        self.assertLessEqual(len(steps_of(p)), 0xFFFF)
        self.assertEqual(mt.apply_patch(base, p), t)

    def test_a_patch_that_reads_past_the_file_is_refused(self):
        base = b"0123456789"
        bad = struct.pack(">HHII", 4, 1, 5, 20)
        with self.assertRaises(mt.ModError):
            mt.apply_patch(base, bad)
        with self.assertRaises(mt.ModError):
            mt.apply_patch(base, struct.pack(">HHII", 3, 1, 0, 1))

    def test_the_base_text(self):
        info = mt.read_base_text(mt.base_text("/WAD/PS3_BE/X.AS", b"abc"))
        self.assertEqual((info["entry"], info["size"]), ("/WAD/PS3_BE/X.AS", "3"))
        self.assertIsNone(mt.base_matches(info, b"abc"))
        self.assertIn("SHA-1", mt.base_matches(info, b"abd"))
        self.assertIn("4 bytes", mt.base_matches(info, b"abcd").replace("has 4", "4 bytes"))


class GameFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.game = os.path.join(d, "PS3_GAME")
        self.disc = os.path.join(self.game, "USRDIR")
        self.upd = os.path.join(d, "updates")
        os.makedirs(self.disc)
        os.makedirs(self.upd)
        self.hero = noise(50000, 4)
        Path(self.disc, "RESOURCES.PSARC").write_bytes(gt.psarc_pack({"/WAD/PS3_BE/R_X.AS": self.hero,
                                                                      "/DC/PS3_BE/A.DCB": b"the disc's"}))
        Path(self.disc, "GAME.PSARC").write_bytes(gt.psarc_pack({"/WAD/PS3_BE/OTHER.WAD": b"x"}))
        Path(self.upd, "PATCHES").write_bytes(b"2")
        Path(self.upd, "TPPS.PSARC").write_bytes(gt.psarc_pack({"/DC/PS3_BE/A.DCB": b"update 0's"}))
        Path(self.upd, "TPPS2.PSARC").write_bytes(gt.psarc_pack({"/DC/PS3_BE/A.DCB.PATCH": b"a patch, not whole"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_game_file_a_patch_goes_over(self):
        self.assertEqual(mt.newest_whole("/WAD/PS3_BE/R_X.AS", self.disc, self.upd), ("RESOURCES.PSARC", self.hero))
        self.assertEqual(mt.newest_whole("/DC/PS3_BE/A.DCB", self.disc, self.upd), ("TPPS.PSARC", b"update 0's"))
        self.assertEqual(mt.newest_whole("/DC/PS3_BE/A.DCB", self.disc, None), ("RESOURCES.PSARC", b"the disc's"))
        self.assertIsNone(mt.newest_whole("/WAD/PS3_BE/NONE.WAD", self.disc, self.upd))

    def test_the_patch_command(self):
        t = bytearray(self.hero)
        t[100:200] = bytes(100)
        t += b"more"
        mine = os.path.join(self.tmp.name, "R_X.AS")
        Path(mine).write_bytes(bytes(t))
        arc = os.path.join(self.tmp.name, "mod", "archive")
        self.assertEqual(mt.main(["patch", mine, "wad\\ps3_be\\r_x.as", arc, "--game", self.game,
                                  "--updates", self.upd]), 0)
        p = Path(arc, "WAD", "PS3_BE", "R_X.AS.PATCH").read_bytes()
        self.assertEqual(mt.apply_patch(self.hero, p), bytes(t))
        info = mt.read_base_text(Path(arc, "WAD", "PS3_BE", "R_X.AS.PATCH.base").read_text(encoding="utf-8"))
        self.assertEqual(info["entry"], "/WAD/PS3_BE/R_X.AS")
        self.assertIsNone(mt.base_matches(info, self.hero))
        # A file the game has not: nothing written.
        self.assertEqual(mt.main(["patch", mine, "/WAD/PS3_BE/NONE.AS", arc, "--game", self.game,
                                  "--updates", self.upd]), 1)
        self.assertFalse(Path(arc, "WAD", "PS3_BE", "NONE.AS.PATCH").exists())


class Textures(unittest.TestCase):
    def test_pictures_that_are_one_file_fold_into_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            same, other = b"\x89PNG one picture", b"\x89PNG another"
            for name, data in (("00000000000000a1_TX1.png", same), ("00000000000000a2_TX2.png", same),
                               ("sub/00000000000000a3.png", same), ("00000000000000b1.png", other),
                               ("atlas.png", same), ("00000000000000a1_z.png", other)):
                Path(d, name).parent.mkdir(parents=True, exist_ok=True)
                Path(d, name).write_bytes(data)
            Path(d, "aliases.txt").write_text("00000000000000c1 atlas.png\n", encoding="utf-8")
            kept, folded, lines = mt.fold_textures(d, dry_run=True)
            self.assertEqual((kept, folded), (2, 2))
            self.assertTrue(Path(d, "00000000000000a2_TX2.png").exists())   # a dry run changes nothing
            kept, folded, lines = mt.fold_textures(d)
            self.assertEqual(lines, ["00000000000000a2 00000000000000a1", "00000000000000a3 00000000000000a1"])
            self.assertFalse(Path(d, "00000000000000a2_TX2.png").exists())
            self.assertFalse(Path(d, "sub", "00000000000000a3.png").exists())
            # Kept: the first by name of each, a second file for a1 (the game takes the first), a picture not named
            # by an id; the list's own line kept, the new ones after it.
            for n in ("00000000000000a1_TX1.png", "00000000000000b1.png", "atlas.png", "00000000000000a1_z.png"):
                self.assertTrue(Path(d, n).exists(), n)
            self.assertEqual(Path(d, "aliases.txt").read_text(encoding="utf-8").splitlines(),
                             ["00000000000000c1 atlas.png"] + lines)
            self.assertEqual(mt.fold_textures(d)[1:], (0, []))   # again: nothing more


FAKE_UPSCALER = r'''
import os, sys
from PIL import Image
src, dst, scale = sys.argv[1], sys.argv[2], int(sys.argv[3])
for f in os.listdir(src):   # a "x4 model": four times whatever is asked
    im = Image.open(os.path.join(src, f))
    im.resize((im.width * 4, im.height * 4), Image.Resampling.NEAREST).save(os.path.join(dst, f))
'''


def dds_info(path):
    """A DDS's size, FourCC and levels from its header."""
    b = Path(path).read_bytes()
    h, w, levels = struct.unpack("<III", b[12:24])[0], struct.unpack("<I", b[16:20])[0], struct.unpack("<I", b[28:32])[0]
    return w, h, b[84:88].decode(), levels


class Upscale(unittest.TestCase):
    """modtools.py upscale on a made-up dump: what is made, what is left out, the files, normal maps, aliases."""

    @classmethod
    def setUpClass(cls):
        try:
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("no Pillow or NumPy")

    def dump(self, d):
        import numpy as np
        from PIL import Image
        os.makedirs(d, exist_ok=True)
        yy, xx = np.mgrid[0:64, 0:64]
        def save(name, a):
            Image.fromarray(a.astype(np.uint8), "RGBA").save(os.path.join(d, name))
        colour = np.stack([xx * 4, yy * 4, (xx + yy) * 2, np.full_like(xx, 255)], -1)
        save("00000000000000c1_64x64_86.png", colour)
        save("00000000000000c2_64x64_86.png", colour)                      # the same texels: an alias
        nx, ny = np.sin(xx / 6.0) * 0.6, np.cos(yy / 5.0) * 0.6             # an AG normal map
        save("00000000000000n1_64x64_88.png".replace("n1", "e1"),
             np.stack([np.full_like(xx, 255), (ny * 0.5 + 0.5) * 255, np.zeros_like(xx), (nx * 0.5 + 0.5) * 255], -1))
        save("00000000000000a1_64x64_88.png", np.stack([xx * 4, yy * 4, xx * 0 + 90, (xx > 31) * 255], -1))
        save("00000000000000f1_64x64_86.png", np.stack([xx * 0 + 50] * 3 + [xx * 0 + 255], -1))   # one colour
        save("00000000000000b8_64x64_81.png", colour)                       # B8: a mask
        save("00000000000000aa_64x64_A5.png", colour)                       # linear: a copy of the frame
        save("00000000000000a2_32x32_86.png", colour[:32, :32])             # small
        save("not-a-dump.png", colour)

    def test_the_mod_it_makes(self):
        from PIL import Image
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            dump, mod = os.path.join(d, "dump"), os.path.join(d, "Up")
            self.dump(dump)
            self.assertEqual(mt.main(["upscale", dump, mod, "--jobs", "2"]), 0)
            tex = os.path.join(mod, "textures")
            self.assertEqual(sorted(os.listdir(tex)), ["00000000000000a1.dds", "00000000000000c1.dds",
                                                       "00000000000000e1.dds", "aliases.txt"])
            self.assertEqual(dds_info(os.path.join(tex, "00000000000000c1.dds")), (128, 128, "DXT1", 8))
            self.assertEqual(dds_info(os.path.join(tex, "00000000000000a1.dds")), (128, 128, "DXT5", 8))
            self.assertEqual(dds_info(os.path.join(tex, "00000000000000e1.dds")), (128, 128, "DXT5", 8))
            self.assertIn("00000000000000c2 00000000000000c1", Path(tex, "aliases.txt").read_text().splitlines())
            self.assertTrue(Path(mod, "mod.ini").read_text().startswith("[mod]\nname = Up\n"))
            # The normal map: red full, blue none, its normals of unit length or less, its relief kept.
            with Image.open(os.path.join(tex, "00000000000000e1.dds")) as im:
                n = np.asarray(im.convert("RGBA")).astype(float)
            x, y = n[..., 3] / 127.5 - 1, n[..., 1] / 127.5 - 1
            self.assertGreater(n[..., 0].mean(), 250)
            self.assertLess(n[..., 2].mean(), 5)
            self.assertLess((x * x + y * y).max(), 1.05)
            self.assertGreater(x.std(), 0.2)
            # Made already: not again; --force makes them again.
            before = os.path.getmtime(os.path.join(tex, "00000000000000c1.dds"))
            self.assertEqual(mt.main(["upscale", dump, mod]), 0)
            self.assertEqual(os.path.getmtime(os.path.join(tex, "00000000000000c1.dds")), before)
            self.assertEqual(Path(tex, "aliases.txt").read_text().count("00000000000000c2"), 1)

    def test_the_players_upscaler_and_png(self):
        with tempfile.TemporaryDirectory() as d:
            dump, mod = os.path.join(d, "dump"), os.path.join(d, "Up")
            self.dump(dump)
            fake = os.path.join(d, "fake_up.py")
            Path(fake).write_text(FAKE_UPSCALER)
            cmd = '"%s" "%s" {in_dir} {out_dir} {scale}' % (sys.executable, fake)
            self.assertEqual(mt.main(["upscale", dump, mod, "--upscaler", cmd, "--format", "png", "--only",
                                      "00000000000000c1,00000000000000a1"]), 0)
            from PIL import Image
            tex = os.path.join(mod, "textures")
            self.assertEqual(sorted(f for f in os.listdir(tex) if f.endswith(".png")),
                             ["00000000000000a1.png", "00000000000000c1.png"])
            with Image.open(os.path.join(tex, "00000000000000c1.png")) as im:
                self.assertEqual(im.size, (128, 128))   # the upscaler's 4x brought to 2x
            # The alpha upscaled apart: its clear half still clear, its drawn half drawn.
            with Image.open(os.path.join(tex, "00000000000000a1.png")) as im:
                a = im.getchannel("A")
            self.assertEqual((a.getpixel((10, 64)), a.getpixel((120, 64))), (0, 255))
            # An upscaler that fails: said, with its command.
            self.assertEqual(mt.main(["upscale", dump, os.path.join(d, "Up2"), "--upscaler", "exit 3"]), 1)

    def test_what_repeats_is_padded_with_its_other_side(self):
        import numpy as np
        xx = np.mgrid[0:64, 0:64][1]
        wave = np.stack([128 + 100 * np.sin(xx * 2 * np.pi / 64)] * 3 + [xx * 0 + 255], -1).astype(np.uint8)
        ramp = np.stack([xx * 4] * 3 + [xx * 0 + 255], -1).astype(np.uint8)
        self.assertTrue(mt.tiles(wave))
        self.assertFalse(mt.tiles(ramp))


if __name__ == "__main__":
    unittest.main()
