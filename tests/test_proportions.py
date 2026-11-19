#!/usr/bin/env python3
"""scripts/proportions.py: a mod's proportions files, from a made-up archive.

The archive is in the WAD form the game's .AS files have: a skeleton entry (type 0x2D) of three joints, with their
names, parents and inverse binds where the game keeps them, and two meshes of it (MG_<skeleton>_*, their data
starting with 0x0001000D and their size). No game file is used.

Usage:
    python tests/test_proportions.py
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import proportions  # noqa: E402

NAMES = ["JORoot1", "JOArm1", "JOHand1"]
PARENTS = [0xFFFF, 0, 1]


def ib(k):
    """Joint k's inverse bind: identity with a translation of its own."""
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -0.5 * k, -1.0 * k, -2.0 * k, 1]


def entry(name, kind, data):
    head = struct.pack(">HHI", 1, kind, len(data)) + name.encode().ljust(56, b"\0")
    pad = (-len(data)) % 16
    return head + data + b"\0" * pad


def skeleton_entry():
    n = len(NAMES)
    b = bytearray(0x24 + 8 * n + 56 * n)
    struct.pack_into(">H", b, 8, n)
    for i, p in enumerate(PARENTS):
        struct.pack_into(">HHHH", b, 0x24 + 8 * i, 0, 0, 0, p)
        b[0x24 + 8 * n + 56 * i:0x24 + 8 * n + 56 * i + len(NAMES[i])] = NAMES[i].encode()
    t = (len(b) + 15) & ~15
    b += b"\0" * (t - len(b))
    struct.pack_into(">I", b, 0x14, t)
    table = bytearray(0x50 + 64 * n)          # the local matrices, which the tool does not read
    off = len(table)
    struct.pack_into(">I", table, 8, off)
    for k in range(n):
        table += struct.pack(">16f", *ib(k))
    return bytes(b + table)


def mesh(size):
    return struct.pack(">IIII", 0x0001000D, size, 0, 0) + b"\0" * (size - 16)


class Proportions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.archive = self.d / "R_TEST.AS"
        self.archive.write_bytes(entry("SK01", 0x2D, skeleton_entry()) + entry("MG_SK01_30000_0", 0x75, mesh(96)) +
                                 entry("MG_SK01_30000_1", 0x75, mesh(160)) + entry("MG_OTHER_30000_0", 0x75, mesh(64)))

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, spec):
        (self.d / "spec.json").write_text(json.dumps(spec))
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "proportions.py"), str(self.archive),
                               str(self.d / "spec.json"), str(self.d / "out")], capture_output=True, text=True)

    def read(self, name):
        b = (self.d / "out" / name).read_bytes()
        self.assertEqual(b[:8], b"GWPROP01")
        ns = struct.unpack_from("<I", b, 8)[0]
        sizes = list(struct.unpack_from("<%dI" % ns, b, 12))
        o = 12 + 4 * ns
        n = struct.unpack_from("<I", b, o)[0]
        o += 4
        joints = []
        for _ in range(n):
            par, ratio = struct.unpack_from("<if", b, o)
            old = list(struct.unpack_from("<16f", b, o + 8))
            new = list(struct.unpack_from("<16f", b, o + 72))
            joints.append((par, round(ratio, 6), old, new))
            o += 136
        self.assertEqual(o, len(b))
        return sizes, joints

    def test_ratios_by_name_the_meshes_and_the_binds(self):
        r = self.run_tool({"SK01": {"ratio": {"JOHand1": 0.5}}})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sizes, joints = self.read("SK01.bin")
        self.assertEqual(sizes, [96, 160])                     # the skeleton's two meshes, not the other one
        self.assertEqual([j[0] for j in joints], [-1, 0, 1])
        self.assertEqual([j[1] for j in joints], [1.0, 1.0, 0.5])
        for k, j in enumerate(joints):                          # its own inverse binds, old and new alike
            self.assertEqual(j[2], ib(k))
            self.assertEqual(j[3], ib(k))

    def test_new_inverse_binds_and_mesh_sizes_given(self):
        binds = [[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, -3.0 * k, 1]] for k in range(3)]
        (self.d / "binds.json").write_text(json.dumps(binds))
        r = self.run_tool({"SK01": {"meshes": [4096], "inverse_binds": "binds.json"}})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sizes, joints = self.read("SK01.bin")
        self.assertEqual(sizes, [4096])
        self.assertEqual(joints[2][2], ib(2))
        self.assertEqual(joints[2][3], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -6.0, 1])

    def test_what_it_turns_away(self):
        for spec, why in (({"SK02": {}}, "no skeleton"), ({"SK01": {"ratio": {"JOFoot1": 0.5}}}, "no joint JOFoot1"),
                          ({"SK01": {"ratio": {"JOArm1": 0}}}, "a ratio of 0"),
                          ({"SK01": {"meshes": list(range(1, 18))}}, "17 mesh sizes")):
            r = self.run_tool(spec)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(why, r.stdout)
        self.assertFalse((self.d / "out" / "SK02.bin").exists())


if __name__ == "__main__":
    unittest.main()
