# Character models: the mesh and skeleton formats, written back and checked in the game (2026-11-19)

## Goal

Can a mod replace a character's model? Map the mesh and skeleton formats far enough to write a mesh the game takes,
and check that against the game itself. Structure only: no model was exported to another format or drawn outside the
game; every decode below ran in memory and gave counts, sizes and errors.

## Method

- **The files:** the WADs of `RESOURCES.PSARC`, read with `scripts/gametext.py`'s PSARC and WAD readers.
- **The streams:** Python ports of the EDGE decoders in `native/` ([index decompression](../../native/spu_edge_idx.c),
  [vertex unpacking](../../native/spu_edge_vtx.c), [skinning](../../native/spu_edge_skin.c) and its
  [palette layout](../../native/spu_edge_skinmat.c)), and encoders written as their inverses.
- **The game:** a measurement build (`gowa.py build --jobcap`, in its own tree through `GOWA_BUILD_DIR`) on the fight
  replay of the [parasite-fight probes](2026-11-18-parasite-fight-probes.md), `SPU_JOB_CAPTURE` of w14-16 from 70 s on,
  450 EDGE jobs a run. A job's own inputs are in its local store at its start: the 22-slot DMA list of the
  [output contract](2026-11-04-edge-output-contract.md). A slot's EA, less the mesh's base in memory, is an offset in
  the WAD's mesh entry.
- The study's scripts are kept outside the tree; an importer would start from them.

## Where the player's body is

- **First level:** `R_PRISONER00.WAD`, mesh `MG_7b771621_0`: 10 parts, 47 segments (45 skinned), about 20,800
  vertices and 32,600 triangles. 75 of a run's 450 jobs read it, and its bytes in memory are the file's.
- `R_HERO00.WAD` holds the hero's shared rigid parts (25 meshes, 120 segments, none skinned), a template skeleton
  (`heroA`, 261 nodes, no inverse binds), the animation entry `ANM_heroa` and sound banks; `R_HERO00.TS` and `.AS` are
  streamed textures and animations.
- The Blades' chains and other forms are WADs of their own: `R_KRATOSCHAINLEFT00`, `R_KRATOSCHAINRIGHT00`,
  `R_FURYKRATOS00`, `R_KRATOSOLIVEWT00`, `R_KRATOSMP`.

## The WAD

As the [game-text note](2026-11-11-game-text.md) has it: a run of entries, each a 64-byte header (u16 tag, u16 flags,
u32 size, a 56-byte name), the data, padding to 16. Tag 1 is a resource, and its flags field is the resource's type;
tags 2 and 3 open and close a group. The types here:

| type | what |
|---|---|
| 0x75 | mesh (`MG_<hash>_0`) |
| 0x83 | model (`MDL_<hash>`) |
| 0x77 | material (`MAT_...`): a shader id and its textures' names |
| 0x16 | texture: a DDS |
| 0x2D | game object; the skeleton is one |
| 0x58 | animation (`ANM_...`) |
| 0x13, 0x42, 0x1F, 0x14 | script components, effects, lights, sound emitters |

## A mesh (type 0x75)

- **Header:** `0x0001000D` (in every mesh seen), the size, 0, 0, the parts' count in the high half of word 4, then from
  word 8 the parts' offsets, `0xFFFF0000` and floats (bounds).
- **A part:** a 0x100-byte head (word 5 the skeleton node it belongs to: a mesh node such as `bodyMesh00`, or a joint
  such as `JOHead1`; floats, bounds), then:
  - one record per segment (a run of the part's joint list, the vertex count, two words not mapped);
  - the RSX-only attributes, each (a self-relative offset, a format word, a size): the UV block, F32 u v a vertex, one
    block for all of the part's segments, which the SPU never reads;
  - a u16 list of the part's joints, the output and input vertex formats, then the segments.
- **A segment:** a 0x70-byte record, then its streams. Every field the EDGE job reads is mapped, each one against its
  DMA slot in all 24 captured segments of the body:

| record | what | slot |
|---|---|---|
| +0x00 | EDGE's segment header: flags (0x83-0x88), hole size in 16 bytes (35-44), the formats' bytes (0xFF: the job's), index kind 2 with no skinning flavour (0x20), matrix format 2, vertex count, index count, 0xFFFFFFFF | 13 |
| +0x10, +0x14 | the index stream, self-relative (both the same); +0x18 its size | 5 |
| +0x20 | the vertex stream, self-relative; +0x28 its size (count x stride, to 16) | 11 |
| +0x34, +0x36 | byte offsets of the two palette pieces in the character's joint matrix array (64 bytes a matrix); +0x38, +0x3A their sizes | 6, 7 |
| +0x3C, +0x40 | size and self-relative offset of the skin weights; 0 for a rigid segment | 10 |
| +0x44, +0x4C | the input and output vertex formats, self-relative; +0x50, +0x54 their sizes | 14, 16 |
| +0x58 | the job's buffer size, at most 0xC000 (the job manager's buffer set) | |
| +0x60..+0x68 | three int32: the fixed-point positions' offsets | |

### The streams

- **Indices:** EDGE's compression ([format](2026-11-03-edge-stages.md)). Encoding it again takes the decoder's rules
  backwards, and they are the original tool's:
  - each triangle's code against the one before it: 0 for (a, c, next), 1 for (c, b, next), 2 for (b, a, next), else 3;
  - a 0 bit for a vertex used for the first time (vertices are numbered in first-use order), a 1 bit and its value
    for any other;
  - the values as eight running sums of their differences, h1 = minus the smallest difference (0 if none is below 0),
    k = the bits of the largest difference + h1;
  - h2 = the bitmask's bits in bytes, rounded up; byte 7 = 0; zero padding to 16.
- **Vertices:** EDGE's attribute blocks: the count, the stride and the blocks after the header; per attribute the
  offset, type, components, EDGE id, size, RSX slot and the fixed block's offset; a fixed block gives each component's
  integer and fraction bits (16 in all). The input types:
  - 2: F32;
  - 4: four 8-bit components (id 20, in one of Kratos's forms);
  - 8: 16-bit fixed point, `(raw + offset) / 2^fraction bits`, with the offsets of +0x60;
  - 9: a unit vector in 3 bytes. Two 10-bit components `A (1 + m 2^-23) + B` (A, B = `0x46352E7C`, `0xC6353150`: about
    -0.707 to 0.707), the left-out one rebuilt as `sqrt(1 - c1^2 - c2^2)`. A 4-bit pattern names its axis (pattern / 4),
    its sign (negative for an even pattern) and w (-1 for pattern % 4 < 2: the tangent's handedness).
  - The body: a type-8 position, a type-9 normal and a type-9 tangent, 12 bytes a vertex.
- **Weights:** 8 bytes a vertex, (weight, index) four times. The weight is /255 and the four sum to 255. The index
  points into the two palette pieces, the first then the second. Empty pairs are (0, 0), at the end.
- **The job's skinning:** `p' = sum of weight/255 x (x q0 + y q1 + z q2 + q3)` over the matrices' rows q0-q3, row
  vectors; a rigid segment goes through slot 18's matrix the same way.

## The skeleton (a type 0x2D entry)

- **Nodes:** the count at +8; from +0x24, 8 bytes a node: flags (0x8000; 0x8020 a joint), first child, next sibling,
  parent (0xFFFF: none). Then 56-byte names, `names[k]` for node k (node 0 the object).
- **Tables:** at +0x14 the offset of a table header (count, count, offset, 3). After the header, a 4x4 a node: a rest
  pose, not the bind pose, since the local transforms the inverse binds imply differ from it. At header + offset, the
  **inverse bind matrices**: row vectors, rigid to 1e-6. The template skeleton of `R_HERO00` has no such table (its
  header ends in 0).
- **Palette matrix k is node k:** of the 14,830 vertices with two or more bones, 99.9% have their two heaviest bones
  next to each other in the tree (71% parent and child, 29% two steps). Shifting k by one breaks that.
- **The bind pose sits on the mesh:** the joints' positions from the inverse binds lie next to the centroids of the
  vertices weighted only to them (hips, knees, ankles, head, wrists); the body stands in a T pose.

## Verification

| check | result |
|---|---|
| decode, the two WADs' 167 segments | indices decode to exactly their vertices, none past them, no degenerate triangle; 66,988 unit vectors of length 1, the left-out component the largest but at 215 quantization ties (within 0.002); 20,352 skinned vertices: weights sum to 255, indices inside the palette, 1-4 bones |
| decode against the game (the capture) | positions from the file, skinned with the job's own palette and the file's weights, equal the job's PUTs within 0.00004 (SPU rounding); rigid segments through slot 18 within 0.00002 |
| byte for byte, every mesh of the level's WADs (the level, `R_PERM`, Megaera, the parasites, the chains, Kratos's forms) | indices 2,103 of 2,103 streams (two with a degenerate triangle among them); vertices 2,103 of 2,103 (660,369 vertices); weights 249 of 249 |
| written back, in the game | below |

The byte-for-byte vertex check carries each unit vector's stored pattern: an encoder that picks the largest component
itself writes 5,138 of 660,369 vertices differently, all at ties, and the decoder takes those as well. The weights keep
their stored order. That is heaviest first, but for 116 vertices whose two weights differ by 1 (127, 128): the rounding
remainder of a 50/50 split.

**The game test.** A test WAD (local, deleted after) had Kratos's body re-encoded in place: every position moved +0.05 in
y, and three segments' weights all on each vertex's heaviest bone. It went in through the
[mods folder](2026-11-18-mods-archive-and-text.md) three times: as a whole WAD, as a one-step `.PATCH`, and once more
with the FIOS cache moved aside. The FIOS cache is the game's 2 GB cache of raw disc-archive blocks in
`vfs/cache/BCES01741/fios`; it was put back after. The replay ran 150 s each time, with no crash. In all three runs
every captured job that read the body (41-83 a run) read the written bytes, and put out the positions computed from the
test WAD within 0.000048; the one job on a one-bone segment did too. Jobs whose triangles EDGE culled put out fewer
indices and were left out of the comparison.

**Pitfall:** parts 2 and 4 (`bodyMesh00`, `bodyMesh01and02`) are twins, and the records are self-relative. A segment
of part 4 therefore also "fits" part 2 at a base 0x40C80 off, and reads as a copy of the mesh with mixed data. Matching
jobs to segments needs the mesh's one base in memory, taken from a segment that occurs once.

## What an importer needs

Done, and shown to work in the game: the index, vertex and weight encoders; the record's fields; the skeleton for
rigging (names, tree, bind pose, palette k = node k); getting the file in through the mods folder.

Still to write:
1. **A segmenter.** At most about 568 vertices, 3,156 indices and 183 palette matrices a segment, as the originals
   have it; the true limit is the job's 48 KB buffer. Each segment's bones must fit two runs of node numbers.
2. **Vertex order.** First-use order of the triangle list, the same in the position, normal, weight and UV streams.
3. **Fixed-point parameters** from the bounding box: the originals put the offset at the minimum and give the integer
   bits the range needs.
4. **The fields not derived yet:** the buffer size (+0x58), the hole size and the flags. The originals' values for the
   same formats will do at first; the formula comes from the job's code.
5. **The part head:** its segment records, the UV record, the joint list and the bounds, for the new segment count.
6. **Materials:** Kratos's own (skin, skirt, bracers) with new pictures through the [textures layer](2026-11-18-mods-textures.md),
   or new `MAT_` and texture entries, which are not mapped.
7. **The WAD:** a larger mesh moves every entry after it. gametext.py writes WADs, but whether anything points at WAD
   offsets is not tested.
8. **Both twins**, and one WAD for each form of Kratos (`R_PRISONER00` is the first level's).
9. **Limits outside the WAD:** a new mesh moves with Kratos's skeleton and animations, so his proportions stay;
   pre-rendered movies keep the old model.

## Verdict

Feasible. The two risks are answered: the formats are mapped field by field, and the game takes a mesh written by
these encoders. What is left is an importer's work, about two to four weeks: segmenting, the part head, the three
fields' formulas and rebuilding the WAD, then a test on each form of Kratos.

## Open points

- The part head's per-segment words, the RSX format words, and which material each part draws with.
- The buffer size, hole size and flags formulas.
- The palettes: for two thirds of the parent-child pairs in the captured palettes, inverse bind x world keeps the bone
  length. The arm chains (clavicle, upper and lower arm) do not, the same way in every job, so those palettes carry
  more (twist helpers). The game builds the palettes itself: a mesh in the same bind space, weighted to the same nodes,
  is skinned as the original is (the end-to-end check above). This matters only for reading animations.
