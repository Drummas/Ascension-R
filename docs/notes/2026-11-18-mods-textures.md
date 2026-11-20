# The mods folder, step 3: pictures in place of the game's textures, and Xbox button icons (2026-11-18)

Steps 1 and 2 ([note](2026-11-18-mods-folder.md), [note](2026-11-18-mods-archive-and-text.md)) took a mod's files and
the entries of the archives. A picture of the game's is inside its WADs and texture streams, named by a hash, and
packed as the game needs it: replacing it there means a mod brings the whole WAD. Step 3 takes it where every texture
passes, on its way to the graphics card, and with it gives #21 its Xbox button icons.

## The id

ps3recomp's `libs/video/rsx_tex_replace.c`: a texture is named by XXH64 of its level 0 as the guest has it (a linear
one's rows without their padding), the seed `format << 48 | width << 24 | height`. The same in every release and run:
the three dumps below gave the same ids for the same textures. XXH64 is written from its specification, and checked
against its published values ("", "abc", the 39-byte sentence, seed 20141025 "xxhash") and a Python version of the
specification.

## The backend

`vp_upload_tex_slot` asks for a picture at each upload of a 2D texture, new or changed, of a format it names:

- **RGBA8**: A8R8G8B8, D8R8G8B8, the packed 16-bit colour formats and DXT1/3/5. Their decoded upload is R, G, B, A
  already (`decode_texel`, and BC decodes so), so a picture goes in as RGBA8 and is sampled through the same
  `rsx_remap_to_d3d` mapping. **R8, R8G8, R16**: B8, G8B8 and X16 keep their own format, the picture's R (and G) in
  it, R16 as R times 257: the mapping stays theirs too.
- **The resource is the picture's**: its size, any, with a full chain made from it (each level the alpha-weighted mean
  of the two by two above, so a clear texel leaves no dark rim). The slot keeps the guest's key and checksum, so a
  change of the guest's bytes still uploads it again, and `repl`, `res_w`, `res_h`, `res_fmt` for the resource; the
  draw's view takes `res_fmt`.
- **The port's hooks** (`rsx_tex_hooks`): `has(id)`, `picture(id, base)`, `dump(id, base)`. Unset, nothing is
  hashed. Level 0 is decoded to RGBA (DXT by its own decoder) only for an overlay or the dump.
- **Churn.** A slot uploaded again four times for a change of its bytes is not asked any more: in the first dump, 151
  of 694 textures were 1280x720 A8R8G8B8 copies of the frame, new every frame; with the rule, 8.
- **One upload of a picture** (2026-11-20). The port gives each picture a key (`rsx_tex_picture.key`, the same for the
  same texels at the same size); the slots of one key hold one resource, `VPTexPic`: the first upload's, its heap
  block and bytes counted once, the others a reference with nothing staged, and the last to go gives the block back.
  Such a resource is never taken over or written again, and a slot letting go of it forgets only the views it named
  (`srvq_forget_slot`). `[tex-stats]` counts the shares. Found with a character mod of 35 files that held 9
  pictures, atlases of 4096x4096 given to each texture of the character: as RGBA8 with their chains they took 1.3 GB
  of the cache's 2 GB, which then let 6-8 textures go and uploaded them again each frame for the first minute of a
  level, each upload decoding its picture again (9-53 ms a frame): 27 flips a second against 57 without the mod on
  the bench route. Shared, the cache peaked at 1.1 GB, the decoding at 0.8 ms a frame: 53 against 55, no dip.

## The port

`port/textures.cpp`: the pictures of the mods that are on (`textures\`, `<id>.png` or `<id>_<anything>.png`, an
`.overlay.png` drawn over the game's own), the first mod's where two have one id, read and written with WIC. A file
is decoded once: known by its size and time and, once read, by its bytes' XXH64, its texels kept by that (a smaller
copy's by its size too) up to `GOWA_PICTURE_CACHE_MB` (512 by default), the least recently used going first; before,
each upload read and decoded it again. An overlay is made over the game's own for each upload and has no key. The
dump on a thread of its own, `textures-dump\<id>_<w>x<h>_<fmt>.png`, once a run for each id (the first dump, written
on the render thread, slowed the fight to 31-37 flips a second and the replay went another way; on its own thread,
42-46). Mods tab: **Write out the game's textures**.

## The game's button icons

Three dumps of the parasite-fight replay on the EU disc: 694, 586 and 731 textures. The buttons the game draws are
64x64 DXT5 textures, a dark disc with the symbol in its colour, the same ones in the menus' hints and, small, in the
tutorial's lines ("Press □ for a Quick Attack."):

| button | id | its picture |
|---|---|---|
| Cross | `d8c17e20cbbe71ac` | A, green |
| Circle | `1f52688dc50e2bfb` | B, red |
| Square | `2133aab0625680af` | X, blue |
| Triangle | `660940394f9aee54` | Y, yellow |
| Select's bar (64x32) | `a4f295497b5454b7` | View |

Square is in the third dump only: in the first two, run slower, Kratos did not get to the tutorial's line with it. The
X16 256x256 textures are the font's pages, made as the game runs, with letters alone; the B8 ones are masks.

**Button icons** (Controls; Auto, PlayStation, Xbox): the port's own icons, 128x128 (the View one 128x64), drawn by
`scripts/button_icons.ps1` with GDI+ to the game's look, a dark disc with a rim and a highlight, and in the exe
(`app.rc`, RCDATA 201 to 205). Auto is Xbox's when an XInput controller is plugged in as the game starts. A mod's
picture of the same texture wins over them. Start, L1/R1, L2/R2 and the sticks were not in these dumps: what draws
them is still to be found.

## The tests

- `tests/test_textures.py` (CI): ps3recomp's `tests/test_rsx_tex_replace.c` (XXH64, a linear texture's id with its
  padding changed, A8R8G8B8, DXT1 with four colours and with three and a clear one, DXT5's alpha, B8, X16, G8B8, the
  packing back, the chain, the hooks), and a driver of `port/textures.cpp` with `mods.cpp`: a whole picture, an overlay
  over a base (its colour, the base where it is clear, a clear texel where its alpha is 1), a mod above winning, a
  file that is no PNG left out and not asked again, the dump written once, the Xbox icons' five ids, and a mod's
  picture of a button winning over the port's.
- The game, the replay with **Button icons: Xbox**: "Press X for a Quick Attack.", "Press Y for a Heavy Attack.",
  "Press B for a Physical Attack." in the tutorial, and the pause menu's "A Select" and "View Back"; the log names the
  five textures given a picture.
