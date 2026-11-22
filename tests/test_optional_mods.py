#!/usr/bin/env python3
"""The mods that come with the port (optional-mods/, "optional mods" in the download): each names itself in its
mod.ini, and Skip intro has an empty boot list (archive/INTRO/BOOT_<id>.TXT) for every release the port takes, so a
release added to scripts/gowa.py's TITLES without one fails here. Their pictures are tests/test_textures.py's.

Usage:
    python tests/test_optional_mods.py
"""
import configparser
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gowa  # noqa: E402

MODS = ROOT / "optional-mods"


class OptionalMods(unittest.TestCase):
    def test_each_names_itself(self):
        mods = sorted(p for p in MODS.iterdir() if p.is_dir())
        self.assertEqual([p.name for p in mods], ["Skip intro", "Xbox button icons"])
        for m in mods:
            ini = configparser.ConfigParser(interpolation=None)
            ini.read(m / "mod.ini", encoding="utf-8")
            for key in ("name", "version", "author", "description"):
                self.assertTrue(ini.get("mod", key, fallback=""), "%s: mod.ini has no %s" % (m.name, key))
            self.assertEqual(ini.get("mod", "name"), m.name)

    def test_skip_intro_has_every_release(self):
        intro = MODS / "Skip intro" / "archive" / "INTRO"
        titles = sorted(t for t, v in gowa.TITLES.items() if v.get("enabled"))
        self.assertEqual(sorted(p.name for p in intro.iterdir()), ["BOOT_%s.TXT" % t for t in titles])
        for t in titles:
            self.assertEqual((intro / ("BOOT_%s.TXT" % t)).stat().st_size, 0, t)


if __name__ == "__main__":
    unittest.main()
