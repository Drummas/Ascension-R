#!/usr/bin/env python3
"""online/tss, the TSS blocks scripts/mp_tss.py builds for the multiplayer (docs/notes/2026-11-22-multiplayer-phase3.md).

Every block blocks.txt names has its JSON file and parses; the Playlist gives every multiplayer mode the Search ids
reach a level list, as the match's level cycle needs ("No valid levels in level cycle" otherwise).

Usage:
    python tests/test_online_tss.py
"""
import json
import unittest
from pathlib import Path

TSS = Path(__file__).resolve().parents[1] / "online" / "tss"


def blocks():
    out = []
    for line in (TSS / "blocks.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, version = line.split()
            out.append((name, int(version)))
    return out


class OnlineTss(unittest.TestCase):
    def test_every_block_has_its_json(self):
        names = [n for n, _ in blocks()]
        self.assertIn("MatchConfig", names)
        self.assertIn("Playlist", names)
        for name in names:
            with self.subTest(block=name):
                json.loads((TSS / (name + ".json")).read_text(encoding="utf-8"))

    def test_versions_the_game_asks_for(self):
        v = dict(blocks())
        self.assertEqual((v["MatchConfig"], v["Playlist"]), (10, 7))

    def test_playlist_levels_for_every_multiplayer_mode(self):
        doc = json.loads((TSS / "Playlist.json").read_text(encoding="utf-8"))
        modes = {m["GameMode"]: m["Levels"] for m in doc["GameModes"]}
        for mode in ("TFR8", "TFR4", "FFR8", "FFR4", "TCTF8", "THUN2", "THUN1", "FVS2"):
            with self.subTest(mode=mode):
                self.assertTrue(modes.get(mode), mode)
                self.assertTrue(all(isinstance(l, str) and l for l in modes[mode]))
                self.assertEqual(len(set(modes[mode])), len(modes[mode]))
        self.assertEqual(len(modes), len(doc["GameModes"]))   # the game refuses a mode listed twice


if __name__ == "__main__":
    unittest.main()
