# What limits a body mesh's size: two memory budgets (2026-11-19)

The [character models note](2026-11-19-character-models.md) measured that a body mesh of 0xB8000 bytes loads and one
of 0xBF000 does not (the body is then not drawn, nothing in the log), and that raising the stream set's resident size
does not help. What sets it was not found. It is not the mesh format, nor the engine: it is two heap sizes in the
game's own configuration files, and both can be raised.

## The probe

Kratos's own three body meshes (`MG_81BC3F6F_30000_0`, `MG_4E90421D_30000_0`, `MG_34AE727F_30000_0` in
`R_HERO00.AS`), unchanged but padded with zeros to a size, each stream set copied to the end of the `.AS` and its game
object pointed there, through a test mod's `archive\`. On the bench route's cinematic:

- **0xB8000**: drawn. **0xBF000**: not drawn, as before.
- The mesh is in memory either way: its head (`0x0001000D`, size) at the same end address, the bigger one 0x7000
  lower, its pages as the file's (but for the record fields fixed up at load) until the run ends. It is loaded and
  not overwritten.
- Only the 0xBF000 run logs `[null-write]` and `[null-read]`: the game copies a 0x2BD0-byte array (the body's 174
  joints of 64 bytes and a 0x50 head) to address 0. `func_002F309C` allocates the character instance's joint array
  through `func_003C4E68` (the heap on top of the heap stack at 0x9C5794) and `func_003C5218` (allocate: a first-fit
  free list, the block's size in words in its first word, the next block at +4), and copies into what it got even
  when that is 0.

## The heaps

Temporary instruction hooks (`ppu_hooks.json`, not kept) on the allocation, on `func_003C4D0C` (a heap made: its
memory, size and name) and on the WAD loader's `func_002FE68C`:

- The array is allocated from the heap **`KratosBodySet(0)_GOSTRM`**, made for the body stream set inside the hero
  WAD's heap. It is 0x106800 bytes; with the 0xBF000 mesh it had 0x4C58 bytes free, the biggest block 0x1DB8, for a
  0x5894-byte request. The mesh, the set's other entries and the instance data share it.
- `func_002F5E34` makes a stream set's heap: its size is the set's slot in a table the game fills from
  **`DC/PS3_BE/WAD_R_FX.DCB`** (GAME.PSARC; the updates do not change it): at 0x7234 a table of 39 (size, hash) pairs,
  among them **0x106800 with hash BE321144 (the body set)** at 0x7254 and 0x43800 with hash 4AB31FA1 (the skirt set)
  at 0x725C. The members' own resident sizes (an object's +0x10C) are not used for it.
- The stream sets' heaps are allocated from **`WAD_R_Hero00`**, the hero WAD's heap: 0xE00000 bytes. A WAD's heap
  size is the WAD's own first entry's (0x100000) unless the game has set an override at 0x9DE284 before loading it,
  which for the hero WAD is the pair **(0xE00000, 0x4B3333)** in **`DC/PS3_BE/WAD_R_PERM.DCB`** (RESOURCES.PSARC, and a
  newer whole copy in each of the EU disc's updates TPPS1, 3, 4 and 5: the newest one is the one to change; at 0x90F64
  in TPPS5's). What the second word sets is not known.
- The WAD heaps are allocated one after another, at 1 MiB boundaries, from the heap **`Levels`**,
  0x75200000..0x7C400000 (114 MiB). `Root` (82 MiB) is the GCM I/O region at 0x70000000 before it.

## Raising them

Through the mods folder's `archive\`, a test mod with both DCB files changed:

| mesh | body set (BE321144) | hero WAD heap | result |
|---|---|---|---|
| 0xBF000 | 0x106800 | 0xE00000 | body not drawn (the joint array) |
| 0xBF000 | 0x180000 | 0xE00000 | body drawn, skirt not drawn (the hero heap short for the skirt set) |
| 0xBF000 | 0x180000 | 0xF00000 | drawn whole, no NULL access |
| 0x180000 (1.5 MiB) | 0x200000 | 0x1000000 | drawn whole, no NULL access |
| 0x300000 (3 MiB) | 0x380000 | 0x1200000 | drawn whole, no NULL access |

The hero WAD heap has to grow with the body set: the set's heap is taken out of it. Raising the 12 MiB entry of the FX
table (1C581F62) changed nothing: it is not one of these heaps.

## What it costs

Every MiB added to the hero WAD's heap moves each later WAD heap of the level up by as much inside `Levels`. In the
opening level, the last WAD heap ends at 0x7B500000 unchanged (15 MiB of `Levels` left) and at 0x7B900000 with the
hero heap 4 MiB bigger (11 MiB left). Other levels load other WADs; the most `Levels` holds in any of them is not
measured, so a mod that adds more than a little is to be played through, or `Levels` made bigger (it is sized at the
game's start, `func_002C1570`; not studied further).
