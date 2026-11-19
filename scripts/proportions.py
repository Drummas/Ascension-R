"""A mod's proportions files (docs/MODDING.md, native/spu_edge_prop.c): a character's bones longer or shorter.

    proportions.py <archive> <spec.json> <the mod's proportions folder>

<archive> is the .AS (or .WAD) that has the skeletons and the meshes: the game's own (R_HERO00.AS for Kratos's body),
or the mod's when it brings meshes of its own. spec.json has an object for each skeleton, by the name of its entry
(type 0x2D) in the archive:

    {
      "81BC3F6F": {
        "ratio": {"JOLeftLowerArm1": 0.8, "JORightLowerArm1": 0.8},
        "meshes": [669568],
        "inverse_binds": "my_binds.json"
      }
    }

- ratio: a joint's new length over its own (its translation from its parent), by its name; every other joint 1.
- meshes (optional): the byte sizes of the meshes whose joints take the proportions; by default every MG_<skeleton>_*
  mesh of the archive (a mesh's data starts with 0x0001000D and its size, which is how the port finds it).
- inverse_binds (optional): a JSON file with a list, a 4x4 per joint (rows, row vectors, the game's axes), the
  inverse binds the meshes are bound with; by default the skeleton's own (meshes bound to the original skeleton:
  their skin follows the bones as they are made longer or shorter).

Each skeleton gives <folder>\\<name>.bin. The port reads the .bin files of every mod that is on.
"""
import json
import os
import struct
import sys

MAGIC = b"GWPROP01"
MAX_JOINTS = 512


def entries(d):
    """[(name, type, offset of the data, size)] of a WAD-form file (a .WAD, an .AS)."""
    o, out = 0, []
    while o + 64 <= len(d):
        tag, fl, size = struct.unpack(">HHI", d[o:o + 8])
        if tag == 1:
            out.append((d[o + 8:o + 64].split(b"\x00")[0].decode("latin-1"), fl, o + 64, size))
        o = (o + 64 + size + 15) & ~15
    return out


def skeleton(d, at, size):
    """A skeleton entry's joints: names, parents (None for a root) and inverse binds (4x4 rows, big-endian floats)."""
    b = d[at:at + size]
    n = struct.unpack_from(">H", b, 8)[0]
    if not n or n > MAX_JOINTS:
        raise ValueError("a skeleton of %d joints" % n)
    par = [struct.unpack_from(">HHHH", b, 0x24 + 8 * i)[3] for i in range(n)]
    par = [None if p == 0xFFFF else p for p in par]
    names = [b[0x24 + 8 * n + 56 * k:0x24 + 8 * n + 56 * k + 56].split(b"\x00")[0].decode("latin-1") for k in range(n)]
    t = struct.unpack_from(">I", b, 0x14)[0]
    off = struct.unpack_from(">I", b, t + 8)[0]
    ib = [list(struct.unpack_from(">16f", b, t + off + 64 * k)) for k in range(n)]
    for k, p in enumerate(par):
        if p is not None and p >= k:
            raise ValueError("joint %d's parent %d comes after it" % (k, p))
    return names, par, ib


def mesh_sizes(d, ents, name):
    """The sizes of the archive's MG_<name>_* meshes."""
    out = []
    for n, t, at, size in ents:
        if n.upper().startswith("MG_%s_" % name.upper()) and size >= 16 and \
                struct.unpack_from(">II", d, at) == (0x0001000D, size):
            out.append(size)
    return sorted(set(out))


def build(names, par, ib, ratio, sizes, ib_new):
    """The file's bytes."""
    n = len(names)
    if not 1 <= len(sizes) <= 16:
        raise ValueError("%d mesh sizes: from 1 to 16" % len(sizes))
    if ib_new is not None and len(ib_new) != n:
        raise ValueError("%d inverse binds for %d joints" % (len(ib_new), n))
    by_name = {nm: k for k, nm in enumerate(names)}
    r = [1.0] * n
    for nm, v in ratio.items():
        if nm not in by_name:
            raise ValueError("no joint %s" % nm)
        if not v > 0:
            raise ValueError("%s: a ratio of %r" % (nm, v))
        r[by_name[nm]] = float(v)
    out = bytearray(MAGIC)
    out += struct.pack("<I", len(sizes)) + struct.pack("<%dI" % len(sizes), *sizes) + struct.pack("<I", n)
    for k in range(n):
        new = ib[k] if ib_new is None else [float(x) for row in ib_new[k] for x in row]
        if len(new) != 16:
            raise ValueError("joint %d's inverse bind is not a 4x4" % k)
        out += struct.pack("<if", -1 if par[k] is None else par[k], r[k])
        out += struct.pack("<16f", *ib[k]) + struct.pack("<16f", *new)
    return bytes(out)


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    archive, spec_path, out = argv[1:]
    d = open(archive, "rb").read()
    ents = entries(d)
    spec = json.load(open(spec_path, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(spec_path))
    os.makedirs(out, exist_ok=True)
    for name, s in spec.items():
        sk = next(((at, size) for n, t, at, size in ents if n.upper() == name.upper() and t == 0x2D), None)
        if not sk:
            print("%s: no skeleton of that name in %s" % (name, archive))
            return 1
        names, par, ib = skeleton(d, *sk)
        sizes = s.get("meshes") or mesh_sizes(d, ents, name)
        ib_new = None
        if s.get("inverse_binds"):
            ib_new = json.load(open(os.path.join(base, s["inverse_binds"]), encoding="utf-8"))
        try:
            data = build(names, par, ib, s.get("ratio", {}), [int(x) for x in sizes], ib_new)
        except ValueError as e:
            print("%s: %s" % (name, e))
            return 1
        path = os.path.join(out, "%s.bin" % name)
        with open(path, "wb") as f:
            f.write(data)
        changed = sum(1 for v in s.get("ratio", {}).values() if v != 1)
        print("%s: %d joints, %d of them another length, meshes of %s bytes, %s inverse binds -> %s" % (
            name, len(names), changed, ", ".join(str(x) for x in sizes), "its own" if ib_new is None else "new", path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
