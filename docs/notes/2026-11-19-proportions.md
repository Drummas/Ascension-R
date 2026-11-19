# Other bone lengths for a character: proportions\ (2026-11-19)

A mod's mesh made for a body of other proportions than Kratos's moves with his bones: its knees bend where his do. The
lengths have to change where the game builds the joints, or where the skinning reads them.

## Where the lengths come from

- **The skeleton entry** (type 0x2D in `R_HERO00.AS`, named by a hash; `81BC3F6F`, `4E90421D` and `34AE727F` are the
  body's): u16 joints at +8, at +0x24 eight bytes a joint (its parent in the fourth u16, 0xFFFF for a root), then 56
  bytes of name a joint; at [+0x14] a table whose +0x50 holds each joint's local 4x4 (to its parent, row vectors, the
  translation in row 3) and whose word at +8 is the offset of the inverse binds, one 4x4 a joint. All eleven body
  skeletons and their multiplayer copies have the same lengths (forearm 0.3552, upper arm 0.4063).
- **Probe 1**: the left forearm 0.3552 -> 0.15 in every body skeleton's local table, and the right one in the WAD's
  template: no change at all in the bench route's cinematic.
- **Probe 2**: the left wrist's inverse bind moved 0.2 towards the elbow: the wrist and hand's skin pulled out by about
  0.2 (25-30 pixels). The inverse binds are the skin's alone.

So the animations carry the lengths (`ANM_heroa`, a container of clips of its own form), and the change belongs after
them: in the joint matrices the skinning takes.

## The skinning job

EDGE's skinned job (job module `e8f44fbc6dbf`, entry 0xAD98, `gowa_edge_job_ad98` in `native/spu_edge_job.c`) has its
input in the local store when it starts (`ej_read`): slot 13 is the segment's record inside the loaded mesh (its +0x34
and +0x36 the palette's byte offsets, +0x38 and +0x3A the sizes of slots 6 and 7); slot 18 the base of the character's
joint matrix array, joint k at base + 64 k; slots 6 and 7 the two pieces of the palette the segment uses (8 and 9 the
last frame's, in a velocity job). A palette matrix is the inverse bind times the joint's world matrix (row vectors), so
world = bind x palette. In memory a mesh starts with 0x0001000D and its size, then two zero words; the record's +0x20
is not relative to the file there.

## The retarget

`native/spu_edge_prop.c`, at each skinned job's start, for a job whose record lies in a mesh of a size a file names:
each joint's world matrix from the array and the original bind, its transform to its parent, the translation times
the joint's ratio, the joints put together again from the root, and the palette made with the file's inverse binds;
the job's copies of slots 6 and 7 (and 8 and 9) written over. Once an array a frame, kept by its address and a hash of
its bytes. The memo's skinned jobs read the palette from the local store later (0xE550) and leave it out of their key,
so a memoised job takes the new palette too. Not covered: the Grotto's own build of the job (0xB7C8).

`scripts/proportions.py` writes the files from the archive's skeleton and a JSON of ratios by name; `port/mods.cpp`
gives the port the `.bin` files of the mods that are on (`GOWA_MOD_PROPORTIONS`).

## Tests

- `tests/test_proportions.py`: a made-up archive, a skeleton of three joints and two meshes of it: ratios by name, the
  meshes found by their header, the skeleton's own inverse binds or the JSON's, and what is turned away (no such
  skeleton or joint, a ratio of 0, more than 16 sizes).
- The game, the bench route's cinematic, a test mod for Kratos's own three body meshes: the elbows at 0.6 shortened
  the upper arms; the wrists at 0.6 brought the hands up to the gauntlets' end, the forearms' skin with them, the
  blades on the back where they were. `[props] a mesh of 669568 bytes at ...: its joints take a mod's proportions`.
