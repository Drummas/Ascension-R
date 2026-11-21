"""A mod's proportions files (docs/MODDING.md, port/skel_prop.c, port/edge_prop.c): a character's bones longer or shorter.

    proportions.py <archive> <spec.json> <the mod's proportions folder>
    proportions.py --binds <archive> <spec.json> <the new archive>

<archive> is the .WAD or .AS that has the skeletons: the game's own, or the mod's when it brings meshes of its own.
spec.json has an object for each skeleton, by the name of its entry (type 0x2D) in the archive, or for an entry
without a name by the name of its first joint (the hero's template skeleton in R_HERO00.WAD, heroA):

    {
      "heroA": {"where": "animation", "ratio": {"JOLeftLowerArm1": 0.8, "JORightLowerArm1": 0.8}},
      "81BC3F6F": {"ratio": {"JOLeftLowerArm1": 0.8}, "meshes": [669568], "inverse_binds": "my_binds.json"}
    }

- ratio: a joint's new length over its own (its translation from its parent), by its name; every other joint 1.
- where: "animation" for a skeleton the animation job puts together (heroA): the joints take the new lengths there,
  so the skin, what hangs on a joint (weapons, chains, the blades on the back) and effects all follow. "skinning"
  (the default) for a mesh's own skeleton (R_HERO00.AS: 81BC3F6F and the other bodies): the skinning job rebuilds
  those meshes' palettes alone, and what hangs on the joints stays where it was.
- meshes ("skinning" only, optional): the byte sizes of the meshes whose joints take the proportions; by default every
  MG_<skeleton>_* mesh of the archive (a mesh's data starts with 0x0001000D and its size, which is how the port finds
  it).
- inverse_binds ("skinning" only, optional): a JSON file with a list, a 4x4 per joint (rows, row vectors, the game's
  axes), the inverse binds the meshes are bound with; by default the skeleton's own (meshes bound to the original
  skeleton: their skin follows the bones as they are made longer or shorter).

The first form writes <folder>\\<name>.bin for each skeleton; the port reads the .bin files of every mod that is on.

--binds writes a copy of the archive in which each skeleton the spec names (but those "where": "animation") has the
rest pose of the new lengths: its local table's translations scaled, its inverse binds made again (the rotations stay).
A mesh modelled in that rest pose needs those binds when "animation" proportions move its joints (with the original
binds its skin would follow the bones as they change, as Kratos's does).
"""
import json
import math
import os
import struct
import sys

MAGIC = b"GWPROP01"
MAGIC_ANIM = b"GWSKEL01"
MAX_JOINTS = 512
MAX_ANIM_JOINTS = 1024


def entries(d):
    """[(name, type, offset of the data, size)] of a WAD-form file (a .WAD, an .AS)."""
    o, out = 0, []
    while o + 64 <= len(d):
        tag, fl, size = struct.unpack(">HHI", d[o:o + 8])
        if tag == 1:
            out.append((d[o + 8:o + 64].split(b"\x00")[0].decode("latin-1"), fl, o + 64, size))
        o = (o + 64 + size + 15) & ~15
    return out


def skeleton(d, at, size, most=MAX_JOINTS):
    """A skeleton entry's joints: names, parents (None for a root) and inverse binds (4x4 rows, big-endian floats;
    None for a skeleton that keeps none, as the template skeletons the animation uses)."""
    b = d[at:at + size]
    n = struct.unpack_from(">H", b, 8)[0]
    if not n or n > most:
        raise ValueError("a skeleton of %d joints" % n)
    par = [struct.unpack_from(">HHHH", b, 0x24 + 8 * i)[3] for i in range(n)]
    par = [None if p == 0xFFFF else p for p in par]
    names = [b[0x24 + 8 * n + 56 * k:0x24 + 8 * n + 56 * k + 56].split(b"\x00")[0].decode("latin-1") for k in range(n)]
    t = struct.unpack_from(">I", b, 0x14)[0]
    off = struct.unpack_from(">I", b, t + 8)[0]
    ib = None
    if t + off + 64 * n <= len(b):
        ib = [list(struct.unpack_from(">16f", b, t + off + 64 * k)) for k in range(n)]
    for k, p in enumerate(par):
        if p is not None and p >= k:
            raise ValueError("joint %d's parent %d comes after it" % (k, p))
    return names, par, ib


def local_table(d, at, size, n):
    """Each joint's local 4x4 to its parent (rows, row vectors, the translation in row 3): the table at [+0x14]."""
    b = d[at:at + size]
    t = struct.unpack_from(">I", b, 0x14)[0]
    if t + 0x50 + 64 * n > len(b):
        raise ValueError("no local table")
    return [list(struct.unpack_from(">16f", b, t + 0x50 + 64 * k)) for k in range(n)]


def find_skeleton(d, ents, name):
    """(offset, size) of the skeleton entry of that name, or of the unnamed one whose first joint has it."""
    for n, t, at, size in ents:
        if t == 0x2D and n.upper() == name.upper():
            return at, size
    for n, t, at, size in ents:
        if t != 0x2D or n or size < 0x24 + 64:
            continue
        cnt = struct.unpack_from(">H", d, at + 8)[0]
        if cnt and 0x24 + 64 * cnt <= size:
            first = d[at + 0x24 + 8 * cnt:at + 0x24 + 8 * cnt + 56].split(b"\x00")[0].decode("latin-1")
            if first.upper() == name.upper():
                return at, size
    return None


def mesh_sizes(d, ents, name):
    """The sizes of the archive's MG_<name>_* meshes."""
    out = []
    for n, t, at, size in ents:
        if n.upper().startswith("MG_%s_" % name.upper()) and size >= 16 and \
                struct.unpack_from(">II", d, at) == (0x0001000D, size):
            out.append(size)
    return sorted(set(out))


def ratios(names, ratio):
    """The spec's ratios by name, as a list in the skeleton's order (1 where it names none)."""
    by_name = {nm: k for k, nm in enumerate(names)}
    r = [1.0] * len(names)
    for nm, v in ratio.items():
        if nm not in by_name:
            raise ValueError("no joint %s" % nm)
        if not 0 < v < 8:
            raise ValueError("%s: a ratio of %r" % (nm, v))
        r[by_name[nm]] = float(v)
    return r


def build(names, par, ib, ratio, sizes, ib_new):
    """A "skinning" file's bytes."""
    n = len(names)
    if ib is None:
        raise ValueError("the skeleton keeps no inverse binds: \"where\": \"animation\" is its kind")
    if not 1 <= len(sizes) <= 16:
        raise ValueError("%d mesh sizes: from 1 to 16" % len(sizes))
    if ib_new is not None and len(ib_new) != n:
        raise ValueError("%d inverse binds for %d joints" % (len(ib_new), n))
    r = ratios(names, ratio)
    out = bytearray(MAGIC)
    out += struct.pack("<I", len(sizes)) + struct.pack("<%dI" % len(sizes), *sizes) + struct.pack("<I", n)
    for k in range(n):
        new = ib[k] if ib_new is None else [float(x) for row in ib_new[k] for x in row]
        if len(new) != 16:
            raise ValueError("joint %d's inverse bind is not a 4x4" % k)
        out += struct.pack("<if", -1 if par[k] is None else par[k], r[k])
        out += struct.pack("<16f", *ib[k]) + struct.pack("<16f", *new)
    return bytes(out)


def fnv64(b):
    h = 1469598103934665603
    for x in b:
        h = ((h ^ x) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def build_anim(d, at, size, names, ratio):
    """An "animation" file's bytes: the joint table's GET size and hash, then each joint's ratio and bind length."""
    n = len(names)
    loc = local_table(d, at, size, n)
    r = ratios(names, ratio)
    out = bytearray(MAGIC_ANIM)
    out += struct.pack("<IIQ", n, (8 * n + 15) & ~15, fnv64(d[at + 0x24:at + 0x24 + 8 * n]))
    for k in range(n):
        out += struct.pack("<ff", r[k], math.sqrt(sum(x * x for x in loc[k][12:15])))
    return bytes(out)


def mul(a, b):
    """Row-vector 4x4s as 16 floats: a then b."""
    return [sum(a[4 * r + i] * b[4 * i + c] for i in range(4)) for r in range(4) for c in range(4)]


def inverse(m):
    a = [list(m[4 * r:4 * r + 4]) + [1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for c in range(4):
        p = max(range(c, 4), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            raise ValueError("a joint's bind does not invert")
        a[c], a[p] = a[p], a[c]
        d = a[c][c]
        a[c] = [x / d for x in a[c]]
        for r in range(4):
            if r != c:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[r][4 + c] for r in range(4) for c in range(4)]


def new_rest(loc, par, r):
    """The local table with the translations scaled, and the inverse binds of that rest pose."""
    loc2, world = [], []
    for k, m in enumerate(loc):
        m2 = list(m)
        for i in (12, 13, 14):
            m2[i] *= r[k]
        loc2.append(m2)
        world.append(m2 if par[k] is None else mul(m2, world[par[k]]))
    return loc2, [inverse(w) for w in world]


def cmd_binds(archive, spec_path, out_path):
    d = bytearray(open(archive, "rb").read())
    ents = entries(bytes(d))
    spec = json.load(open(spec_path, encoding="utf-8"))
    done = 0
    for name, s in spec.items():
        if s.get("where", "skinning") == "animation":
            continue
        sk = find_skeleton(bytes(d), ents, name)
        if not sk:
            print("%s: no skeleton of that name in %s" % (name, archive))
            return 1
        at, size = sk
        try:
            names, par, ib = skeleton(bytes(d), at, size)
            if ib is None:
                raise ValueError("the skeleton keeps no inverse binds")
            loc = local_table(bytes(d), at, size, len(names))
            loc2, ib2 = new_rest(loc, par, ratios(names, s.get("ratio", {})))
        except ValueError as e:
            print("%s: %s" % (name, e))
            return 1
        t = struct.unpack_from(">I", d, at + 0x14)[0]
        off = struct.unpack_from(">I", d, at + t + 8)[0]
        for k in range(len(names)):
            struct.pack_into(">16f", d, at + t + 0x50 + 64 * k, *loc2[k])
            struct.pack_into(">16f", d, at + t + off + 64 * k, *ib2[k])
        moved = max(math.dist(inverse(a)[12:15], inverse(b)[12:15]) for a, b in zip(ib, ib2))
        print("%s: %d joints, the rest pose of the new lengths (joints moved up to %.4f)" % (name, len(names), moved))
        done += 1
    with open(out_path, "wb") as f:
        f.write(d)
    print("%d skeletons -> %s" % (done, out_path))
    return 0


def main(argv):
    if len(argv) == 5 and argv[1] == "--binds":
        return cmd_binds(*argv[2:])
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
        sk = find_skeleton(d, ents, name)
        if not sk:
            print("%s: no skeleton of that name in %s" % (name, archive))
            return 1
        where = s.get("where", "skinning")
        if where not in ("skinning", "animation"):
            print("%s: where is \"skinning\" or \"animation\", not %r" % (name, where))
            return 1
        changed = sum(1 for v in s.get("ratio", {}).values() if v != 1)
        path = os.path.join(out, "%s.bin" % name)
        try:
            if where == "animation":
                names = skeleton(d, *sk, most=MAX_ANIM_JOINTS)[0]
                data = build_anim(d, sk[0], sk[1], names, s.get("ratio", {}))
                note = "where the animation puts them together"
            else:
                names, par, ib = skeleton(d, *sk)
                sizes = s.get("meshes") or mesh_sizes(d, ents, name)
                ib_new = None
                if s.get("inverse_binds"):
                    ib_new = json.load(open(os.path.join(base, s["inverse_binds"]), encoding="utf-8"))
                data = build(names, par, ib, s.get("ratio", {}), [int(x) for x in sizes], ib_new)
                note = "meshes of %s bytes, %s inverse binds" % (", ".join(str(x) for x in sizes),
                                                               "its own" if ib_new is None else "new")
        except ValueError as e:
            print("%s: %s" % (name, e))
            return 1
        with open(path, "wb") as f:
            f.write(data)
        print("%s: %d joints, %d of them another length, %s -> %s" % (name, len(names), changed, note, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
