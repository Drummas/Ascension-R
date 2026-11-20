#!/usr/bin/env python3
"""scripts/modpack.py: the mods' archive\\ and text\\ as one more update, on a made-up game folder.

The folder is test_gametext's: PATCHES (5) and a TPPS5.PSARC with the English text patches, here with the English (UK)
ones beside them (a line fewer) and the .PATCH names of a WAD and a texture stream the updates change. No game file
is used.

Usage:
    python tests/test_modpack.py
"""
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import gametext as gt  # noqa: E402
import modpack  # noqa: E402
import modtools  # noqa: E402
from test_gametext import MSGS, MP, SP, patch  # noqa: E402

SP_GB = gt.WAD_DIR + "R_LANG_EN-GB.WAD.PATCH"
MP_GB = gt.WAD_DIR + "R_LANG_EN-GB_MP.WAD.PATCH"
# English (UK): a line spelt its own way.
MSGS_GB = MSGS.replace(b"Options...", b"Optionz...")


def put(path, data=b"x"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


class Pack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.usr = os.path.join(self.d, "game", "USRDIR")
        os.makedirs(self.usr)
        Path(self.usr, "PATCHES").write_bytes(b"5")
        self.sp, self.mp = patch(MSGS, 0xBBA20), patch(MSGS, 0xCCE40)
        files = {SP: self.sp, MP: self.mp, SP_GB: patch(MSGS_GB, 0xBBA20), MP_GB: patch(MSGS_GB, 0xCCE40),
                 "/WAD/PS3_BE/SHELL.WAD.PATCH": b"an update's patch", "/WAD/PS3_BE/SHELL.TS.PATCH": b"and another"}
        Path(self.usr, "TPPS5.PSARC").write_bytes(gt.psarc_pack(files))
        Path(self.usr, "TPPS.PSARC").write_bytes(gt.psarc_pack({"/DC/PS3_BE/X.DCB": b"the game's"}))
        # The disc's archives: a hero file no update changes, and the DCB an update brings whole again.
        self.disc = os.path.join(self.d, "disc", "USRDIR")
        os.makedirs(self.disc)
        self.hero = bytes(range(256)) * 400
        Path(self.disc, "RESOURCES.PSARC").write_bytes(gt.psarc_pack({"/WAD/PS3_BE/R_X.AS": self.hero,
                                                                      "/DC/PS3_BE/X.DCB": b"the disc's"}))
        self.out = os.path.join(self.d, "built")

    def tearDown(self):
        self.tmp.cleanup()

    def mod(self, name, files):
        root = os.path.join(self.d, "mods", name)
        for rel, data in files.items():
            put(os.path.join(root, rel), data)
        return {"id": name, "archive": os.path.join(root, "archive") if os.path.isdir(os.path.join(root, "archive")) else None,
                "text": os.path.join(root, "text") if os.path.isdir(os.path.join(root, "text")) else None}

    def pack(self, *mods, updates=5):
        res = modpack.pack({"usrdir": self.usr, "disc": self.disc, "updates": updates, "mods": list(mods)}, self.out,
                           log=lambda s: None)
        arc = os.path.join(self.out, "files", "TPPS%d.PSARC" % (updates + 1))
        names = gt.psarc_names(arc) if os.path.isfile(arc) else []
        return res, names, arc

    def test_entries_the_updates_patch_go_in_as_one_step_patches(self):
        a = self.mod("A", {"archive/wad/ps3_be/shell.wad": b"my shell", "archive/WAD/PS3_BE/SHELL.TS": b"my textures",
                           "archive/DC/PS3_BE/X.DCB": b"my dcb", "archive/WAD/PS3_BE/NEW.WAD": b"a new one",
                           "archive/WAD/PS3_BE/OWN.WAD.PATCH": b"its own patch", "archive/Thumbs.db": b"litter"})
        b = self.mod("B", {"archive/WAD/PS3_BE/SHELL.WAD": b"another shell", "archive/OTHER.BIN": b"b's"})
        res, names, arc = self.pack(a, b)
        self.assertEqual(res[0], ["update", 6, 6])
        self.assertIn(["archive", "A", 5, 2, 0, "-"], res)
        self.assertIn(["archive", "B", 1, 0, 1, "/WAD/PS3_BE/SHELL.WAD"], res)   # A, above, has it
        self.assertEqual(sorted(names), ["/DC/PS3_BE/X.DCB", "/OTHER.BIN", "/WAD/PS3_BE/NEW.WAD", "/WAD/PS3_BE/OWN.WAD.PATCH",
                                         "/WAD/PS3_BE/SHELL.TS.PATCH", "/WAD/PS3_BE/SHELL.WAD.PATCH"])
        got = gt.psarc_read(arc, set(names))
        self.assertEqual(got["/WAD/PS3_BE/SHELL.WAD.PATCH"], struct.pack(">HHII", 4, 1, 0x80000000, 8) + b"my shell")
        self.assertEqual(got["/WAD/PS3_BE/OWN.WAD.PATCH"], b"its own patch")
        self.assertEqual((got["/DC/PS3_BE/X.DCB"], got["/WAD/PS3_BE/NEW.WAD"]), (b"my dcb", b"a new one"))
        self.assertEqual(Path(self.out, "files", "PATCHES").read_bytes(), b"6")

    def test_a_patch_with_its_base_goes_in_for_that_copy_of_the_game_only(self):
        mine = bytearray(self.hero)
        mine[1000:1100] = b"\x00" * 100
        mine = bytes(mine) + b"added"
        p = modtools.make_patch(self.hero, mine)
        a = self.mod("A", {"archive/WAD/PS3_BE/R_X.AS.PATCH": p,
                           "archive/WAD/PS3_BE/R_X.AS.PATCH.base": modtools.base_text("/WAD/PS3_BE/R_X.AS", self.hero)})
        res, names, arc = self.pack(a)
        self.assertIn(["archive", "A", 1, 0, 0, "-"], res)
        self.assertEqual(names, ["/WAD/PS3_BE/R_X.AS.PATCH"])   # the .base is not an entry
        got = gt.psarc_read(arc, set(names))["/WAD/PS3_BE/R_X.AS.PATCH"]
        self.assertEqual(modtools.apply_patch(self.hero, got), mine)
        # Made for another copy of the file: left out, and said why.
        b = self.mod("B", {"archive/WAD/PS3_BE/R_X.AS.PATCH": p,
                           "archive/WAD/PS3_BE/R_X.AS.PATCH.base": modtools.base_text("/WAD/PS3_BE/R_X.AS",
                                                                                        self.hero[:-1] + b"?")})
        res, names, _ = self.pack(b)
        self.assertIn(["error", "B", "R_X.AS.PATCH: made for another copy of the file (its SHA-1 differs)"], res)
        self.assertEqual((res[0], names), (["update", 0, 0], []))
        # The file a patch goes over is the newest update's that brings it whole, not the disc's.
        c = self.mod("C", {"archive/DC/PS3_BE/X.DCB.PATCH": modtools.make_patch(b"the game's", b"the mod's"),
                           "archive/DC/PS3_BE/X.DCB.PATCH.base": modtools.base_text("/DC/PS3_BE/X.DCB", b"the game's")})
        d = self.mod("D", {"archive/WAD/PS3_BE/R_Y.AS.PATCH": p,
                           "archive/WAD/PS3_BE/R_Y.AS.PATCH.base": modtools.base_text("/WAD/PS3_BE/R_Y.AS", b"")})
        res, names, _ = self.pack(c, d)
        self.assertIn(["archive", "C", 1, 0, 0, "-"], res)
        self.assertIn(["error", "D", "R_Y.AS.PATCH: the game has no /WAD/PS3_BE/R_Y.AS"], res)
        self.assertEqual(names, ["/DC/PS3_BE/X.DCB.PATCH"])

    def test_text_lines_first_mod_first_and_english_for_both(self):
        a = self.mod("A", {"text/en.tsv": "1.1\tJeda\n2.1\tTekan [XButton] untuk melompat\n3.1\tTidak ada\n"})
        b = self.mod("B", {"text/en-menus.tsv": "1.1\tLain\n2.2\tPilihan...\n"})
        res, names, arc = self.pack(a, b, updates=7)   # a mod brought a seventh update: this is the eighth
        self.assertEqual(res[0][:2], ["update", 8])
        self.assertIn(["text", "A", "EN", 2, 1, "3.1: no such line in the game's text"], res)
        self.assertIn(["text", "B", "EN", 1, 1, "1.1: a mod above has it"], res)
        # English (UK) too, where its lines are: a line it has not is said under EN, not again.
        self.assertIn(["text", "A", "EN-GB", 2, 0, "-"], res)
        self.assertIn(["text", "B", "EN-GB", 1, 1, "1.1: a mod above has it"], res)
        got = gt.psarc_read(arc, {SP, MP, SP_GB, MP_GB})
        self.assertEqual(sorted(got), sorted([SP, MP, SP_GB, MP_GB]))
        for nm in (SP, MP, SP_GB):
            lines = gt.patch_msgs(got[nm]).decode().split("\r\n")
            self.assertIn("Jeda", lines)
            self.assertIn("Tekan [XButton] untuk melompat", lines)
            self.assertIn("Pilihan...", lines)
            self.assertNotIn("Lain", lines)
        self.assertEqual(got[MP][20:24], struct.pack(">I", 0xCCE40))   # each patch keeps its own steps

    def test_a_language_the_game_lacks_and_a_language_a_mod_brings_whole(self):
        a = self.mod("A", {"text/fr/menus.tsv": "1.1\tPause\n"})
        res, names, _ = self.pack(a)
        self.assertIn(["error", "A", "the game has no FR text"], res)
        self.assertEqual(res[0], ["update", 0, 0])   # nothing to pack: no update
        b = self.mod("B", {"archive/WAD/PS3_BE/R_LANG_EN.WAD": b"a whole text"})
        c = self.mod("C", {"text/en-gb.tsv": "1.1\tJeda\n2.1\tTekan [XButton] untuk melompat\n"})
        res, names, _ = self.pack(b, c)
        self.assertIn(["text", "C", "EN-GB", 2, 0, "-"], res)
        c2 = self.mod("C2", {"text/en.tsv": "1.1\tJeda\n"})
        res, _, _ = self.pack(b, c2)
        self.assertIn(["text", "C2", "EN", 0, 1, "B brings the EN text whole"], res)

    def test_languages_by_name(self):
        self.assertEqual([modpack.lang_of(n) for n in ("en", "EN-GB-story", "en-story", "es-la", "es_menus", "pt-br.x",
                                                       "english", "zh")],
                         ["EN", "EN-GB", "EN", "ES-LA", "ES", "PT-BR", None, "ZH"])

    def test_the_command(self):
        a = self.mod("A", {"archive/DC/PS3_BE/X.DCB": b"mine", "text/en.tsv": "1.1\tJeda\n"})
        inp = os.path.join(self.d, "input.txt")
        Path(inp).write_text("usrdir\t%s\nupdates\t5\nmod\tA\t%s\t%s\n" % (self.usr, a["archive"], a["text"]),
                             encoding="utf-8")
        self.assertEqual(modpack.main(["modpack.py", inp, self.out]), 0)
        lines = Path(self.out, "result.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "update\t6\t5")   # the DCB, and the two English patches and the two English (UK)
        self.assertIn("archive\tA\t1\t0\t0\t-", lines)
        self.assertIn("text\tA\tEN\t1\t0\t-", lines)
        # Packed again with nothing: the old update is gone.
        Path(inp).write_text("usrdir\t%s\nupdates\t5\n" % self.usr, encoding="utf-8")
        self.assertEqual(modpack.main(["modpack.py", inp, self.out]), 0)
        self.assertEqual(os.listdir(os.path.join(self.out, "files")), [])


if __name__ == "__main__":
    unittest.main()
