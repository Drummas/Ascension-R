#!/usr/bin/env python3
"""scripts/proportions.py: a mod's proportions files, from a made-up archive.

The archive is in the WAD form the game's .AS files have: a skeleton entry (type 0x2D) of three joints, with their
names, parents, local matrices and inverse binds where the game keeps them, two meshes of it (MG_<skeleton>_*, their
data starting with 0x0001000D and their size), and an unnamed template skeleton of four joints that keeps no inverse
binds, as R_HERO00.WAD's heroA. No game file is used.

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


def local(k):
    """Joint k's local matrix: the root at the origin, each other 0.5, 1, 2 from its parent (so ib(k)'s bind)."""
    t = (0.0, 0.0, 0.0) if k == 0 else (0.5, 1.0, 2.0)
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, t[0], t[1], t[2], 1]


def skeleton_entry(names=NAMES, parents=PARENTS, binds=True):
    n = len(names)
    b = bytearray(0x24 + 8 * n + 56 * n)
    struct.pack_into(">H", b, 8, n)
    for i, p in enumerate(parents):
        struct.pack_into(">HHHH", b, 0x24 + 8 * i, 0x8000 | i, 0, 0, p)
        b[0x24 + 8 * n + 56 * i:0x24 + 8 * n + 56 * i + len(names[i])] = names[i].encode()
    t = (len(b) + 15) & ~15
    b += b"\0" * (t - len(b))
    struct.pack_into(">I", b, 0x14, t)
    table = bytearray(0x50)
    for k in range(n):
        table += struct.pack(">16f", *local(k))
    struct.pack_into(">I", table, 8, len(table))   # the inverse binds' offset: past the end when there are none
    if binds:
        for k in range(n):
            table += struct.pack(">16f", *ib(k))
    return bytes(b + table)


TEMPLATE = ["tmplA", "JOArm1", "JOHand1", "handWeapon1"]


def mesh(size):
    return struct.pack(">IIII", 0x0001000D, size, 0, 0) + b"\0" * (size - 16)


class Proportions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.archive = self.d / "R_TEST.AS"
        self.archive.write_bytes(entry("SK01", 0x2D, skeleton_entry()) + entry("MG_SK01_30000_0", 0x75, mesh(96)) +
                                 entry("MG_SK01_30000_1", 0x75, mesh(160)) + entry("MG_OTHER_30000_0", 0x75, mesh(64)) +
                                 entry("", 0x2D, skeleton_entry(TEMPLATE, [0xFFFF, 0, 1, 2], binds=False)))

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, spec, *first):
        (self.d / "spec.json").write_text(json.dumps(spec))
        out = self.d / ("new.AS" if first else "out")
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "proportions.py"), *first, str(self.archive),
                               str(self.d / "spec.json"), str(out)], capture_output=True, text=True)

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
                          ({"SK01": {"meshes": list(range(1, 18))}}, "17 mesh sizes"),
                          ({"tmplA": {"ratio": {"JOArm1": 0.5}}}, "keeps no inverse binds"),
                          ({"SK01": {"where": "elsewhere"}}, "not 'elsewhere'")):
            r = self.run_tool(spec)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(why, r.stdout)
        self.assertFalse((self.d / "out" / "SK02.bin").exists())

    def test_animation_file_for_an_unnamed_template_by_its_first_joint(self):
        r = self.run_tool({"tmplA": {"where": "animation", "ratio": {"JOHand1": 0.5, "handWeapon1": [0.5, 1, 2]}}})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = (self.d / "out" / "tmplA.bin").read_bytes()
        self.assertEqual(b[:8], b"GWSKEL01")
        n, table, h = struct.unpack_from("<IIQ", b, 8)
        self.assertEqual((n, table), (4, 32))                  # the table's GET: 8 bytes a joint, to 16
        a = self.archive.read_bytes()
        at = [o for name, t, o, size in proportions.entries(a) if t == 0x2D and not name][0]
        self.assertEqual(h, proportions.fnv64(a[at + 0x24:at + 0x24 + 8 * 4]))
        joints = [struct.unpack_from("<3ff", b, 24 + 16 * k) for k in range(4)]
        self.assertEqual(len(b), 24 + 16 * 4)
        self.assertEqual([tuple(round(x, 6) for x in j[:3]) for j in joints],
                         [(1, 1, 1), (1, 1, 1), (0.5, 0.5, 0.5), (0.5, 1, 2)])   # one ratio, or one for each axis
        self.assertEqual([round(j[3], 4) for j in joints], [0.0, 2.2913, 2.2913, 2.2913])   # |(0.5, 1, 2)|

    def test_three_ratios_are_not_for_the_skinning_files(self):
        r = self.run_tool({"SK01": {"ratio": {"JOArm1": [0.5, 1, 1]}}})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("three ratios are for", r.stdout)
        r = self.run_tool({"SK01": {"ratio": {"JOArm1": [0.5, 0.5, 0.5]}}})       # the same three: one ratio
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_binds_keep_a_joint_without_an_inverse_bind(self):
        b = bytearray(self.archive.read_bytes())
        at, size = proportions.find_skeleton(bytes(b), proportions.entries(bytes(b)), "SK01")
        t = struct.unpack_from(">I", b, at + 0x14)[0]
        off = struct.unpack_from(">I", b, at + t + 8)[0]
        struct.pack_into(">16f", b, at + t + off + 64 * 2, *[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
        self.archive.write_bytes(bytes(b))                    # the hand: no inverse bind, as the skin does not ride it
        r = self.run_tool({"SK01": {"ratio": {"JOArm1": 0.5}}}, "--binds")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 without an inverse bind kept so", r.stdout)
        a = (self.d / "new.AS").read_bytes()
        ibs = proportions.skeleton(a, at, size)[2]
        self.assertEqual(ibs[2], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
        self.assertEqual([round(x, 6) for x in ibs[1][12:15]], [-0.25, -0.5, -1.0])
        self.assertEqual(proportions.local_table(a, at, size, 3)[2][12:15], [0.5, 1.0, 2.0])

    def test_binds_every_copy_of_the_skeleton(self):
        a = self.archive.read_bytes()
        self.archive.write_bytes(a + entry("SK01", 0x2D, skeleton_entry()))   # a stream set's copy at the end
        r = self.run_tool({"SK01": {"ratio": {"JOArm1": 0.5}}}, "--binds")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 skeletons", r.stdout)
        b = (self.d / "new.AS").read_bytes()
        found = [(at, size) for n, t, at, size in proportions.entries(b) if t == 0x2D and n == "SK01"]
        self.assertEqual(len(found), 2)
        for at, size in found:
            self.assertEqual(proportions.local_table(b, at, size, 3)[1][12:15], [0.25, 0.5, 1.0])
            self.assertEqual([round(x, 6) for x in proportions.skeleton(b, at, size)[2][1][12:15]], [-0.25, -0.5, -1.0])

    def test_binds_the_rest_pose_of_the_new_lengths(self):
        r = self.run_tool({"SK01": {"ratio": {"JOArm1": 0.5, "JOHand1": [1, 1, 0.5]}}, "tmplA": {"where": "animation"}},
                          "--binds")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = (self.d / "new.AS").read_bytes()
        at, size = proportions.find_skeleton(a, proportions.entries(a), "SK01")
        names, par, ibs = proportions.skeleton(a, at, size)
        loc = proportions.local_table(a, at, size, 3)
        self.assertEqual(loc[1][12:15], [0.25, 0.5, 1.0])     # the arm half as long
        self.assertEqual(loc[2][12:15], [0.5, 1.0, 1.0])      # the hand: its z alone halved
        self.assertEqual([round(x, 6) for x in ibs[1][12:15]], [-0.25, -0.5, -1.0])
        self.assertEqual([round(x, 6) for x in ibs[2][12:15]], [-0.75, -1.5, -2.0])
        self.assertEqual(len(a), self.archive.stat().st_size)
        self.assertIn("0 without an inverse bind kept so", r.stdout)
        old = self.archive.read_bytes()
        tat = [o for name, t, o, s in proportions.entries(old) if t == 0x2D and not name][0]
        self.assertEqual(a[tat:tat + 400], old[tat:tat + 400])   # the "animation" one is not the archive's to change


if __name__ == "__main__":
    unittest.main()
