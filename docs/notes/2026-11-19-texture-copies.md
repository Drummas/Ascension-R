# The game's copies of a texture, and the textures layer (2026-11-19)

A mod gave Kratos's body textures pictures of its own ([step 3](2026-11-18-mods-textures.md)), by the ids the dump
wrote. In the opening level's in-engine cinematic, parts of the body still showed Kratos's: his armour's colours on the
mod's cloth, his muscles in the normals and the shading of the chest, his face's occlusion on the face.

## What the draws sampled

`rsxcap` (ps3recomp `libs/video/rsx_d3d12_backend.c`, `RSX_CAP_SHOT=1` with `RSX_CAP_DIR`) now puts each sampled
texture's id beside it in the manifest, `t<n> off=... <w>x<h> ... id=<id>`, worked out from the guest's bytes as the
capture is taken. The body's draws sampled, beside the mod's pictures, eleven textures of the hero's that no material
of `R_HERO00.AS` names by these ids: a 512x1024 and a 256x512 normal map of the chest, a 128x256 occlusion of it,
256x256 normals and occlusion of the face, 256x256 and 128x128 ones of the armour, its 256x256 colour.

They lay in one run of the RSX's memory, one after another, with two textures the hero's materials name whose data is
not in its stream (`TXFC204D79`, `TX01243D74`): a WAD's textures, loaded as a whole.

## Where they are

A level's WAD holds textures of the hero's under the same names as `R_HERO00.AS`, but only their small levels: the
2048x4096 `TX7F293F72` (the chest's normals) is 699,264 bytes in `HECA825IGC.WAD` and `R_KRATOSOLIVEWT00.WAD`, its
levels from 512x1024 down to 1x1 after the 208-byte head. The stub's first word, the level 0 offset in a stream, is
not -1; the game takes the stream's levels when they have arrived, and until then draws with these, as a texture of
512x1024. Its id is XXH64 of that 512x1024 level, not of the stream's, whose small levels are coded apart (the
stream's 512x1024 level hashes to another id).

Seven of the eleven are such tails, all from level 2 (`TX7F293F72`, `TX96DB8AF9`, `TXAF82A686`, `TXC3A129BF`,
`TXDEE87EFB`, `TXE135CA11`, `TXFB9568CA`); two are whole textures held only in WADs (`TXFC204D79`, `TX01243D74`). Two
(a 256x512 and a 256x256 DXT5) are in no archive's entry, whole or as a tail, nor any level of one: still to be found.

## The table and the layer

`scripts/texture_copies.py` reads every `.AS` (with its `.TS`) and `.WAD` of the base archives and, for each texture
entry of DXT1/3/5, works out the id of its first level present: the stream's level 0, a whole one inline, or a tail's
first (the level whose chain down to 1x1 the entry's bytes are, within 64 bytes). Textures of one name with more than
one id go into `port/texture_copies.inc`: on the EU disc's (BCES01741 01.00), 6,214 names, 329 with copies of more than
one id, 660 copies, in 2 minutes 15 seconds.

`port/textures.cpp` gives each of a texture's copies that has no picture of its own the picture of a copy that has one,
with the size of that copy; a smaller copy gets the picture smaller by as much, each texel the mean of those it covers.
The `[tex]` line counts them: `for N textures (K of them other copies of the game's)`.

## Tests

- `tests/test_textures.py`: a picture for a texture's whole copy taken by its level 2 copy at a quarter of its size, its
  halves kept; a copy with a picture of its own keeping it; a small copy's picture going to the whole one as it is.
- The game, the bench route's cinematic, a test mod of two flat colours for the stream ids of the chest's and the
  armour's colour: `[tex] 2 pictures of mods ... for 4 textures (2 of them other copies of the game's)`, the 256x256
  copy of the armour's colour given its picture at 256x256 and a 512x1024 copy of the chest's at 256x512, and every
  shot of the cinematic in the two colours.
