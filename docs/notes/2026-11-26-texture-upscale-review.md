# Upscaled textures: what a pack needs (2026-11-26)

Item 8 of the [graphics upgrades plan](2026-11-24-graphics-upgrades-plan.md): sharper textures made by an upscaler
from the player's own dump, put back through the mods folder. Before any code: the texture replacement path as it is
([mods textures](2026-11-18-mods-textures.md)), what the dumps hold, and one measured run with a stand-in pack.

## What the game's textures are

The dump of the first levels in `build-jobcap\textures-dump` (869 textures; `build\textures-dump`, 502, is the same
mix), sorted by their texels (`build\issues\texup\dump_stats.py`):

| kind | textures | level 0 | |
|---|---|---|---|
| colour, DXT1 (`86`) | 544 | 141 Mtexels | walls, floors, characters; some grey (masks, detail) and effect sheets (smoke, fire) on black |
| normal maps, DXT5 (`88`) | 172 | 62 Mtexels | stored **AG**: R 255, G the normal's y, B 0, alpha its x; the dump shows them orange with the relief in alpha |
| alpha, DXT5 | 63 | 4 Mtexels | cut-outs (foliage, chains, the button icons) and blends |
| masks, B8 (`81`) | 49 | 8 Mtexels | |
| flat | 28 | 4 Mtexels | one colour |
| frame copies (`A5`, `B4`) | 12 | 8 Mtexels | 1280x720 copies of the frame, targets |

Sizes: mostly 128 to 1024, a few 2048x2048.

## The path today

- A texture is known by XXH64 of its level 0 (with format and size); `textures\<id>.png`, `aliases.txt` and the
  texture copies (`texture_copies.inc`) give it a picture.
- The picture is a PNG read with WIC **on the render thread** at the texture's first upload, its texels kept up to
  `GOWA_PICTURE_CACHE_MB` (512); uploaded as **RGBA8** with a chain the CPU makes (`rsx_tex_mip_down`); the texture
  cache may take a third of the VRAM, at most 2 GB (`vp_tex_budget`).
- RGBA8 is 8 times DXT1 and 4 times DXT5. For the 587 textures of that dump worth upscaling (colour, normal maps,
  alpha; 64 or more on a side), with their chains:

  | | RGBA8 | BC1 for DXT1, BC7 for DXT5 |
  |---|---|---|
  | the game's own (DXT) | | 0.09 GB |
  | 2x | 2.89 GB | 0.37 GB |
  | 4x | 11.6 GB | 1.5 GB |

## Measured: a stand-in pack

`build\issues\texup\make_test_pack.py`: 837 pictures from both dumps at 2x (Lanczos, standing in for an upscaler's
output of the same size), the colour ones tinted magenta so that a surface left unreplaced shows; 1.1 GB of PNG. The
bench route (Profile 1's checkpoint), i5-12400F, RX 6700 XT, this PC's settings, one run each:

| | bench median | flips at t=100 / 130 s (thread report) | `rsx render` thread |
|---|---|---|---|
| no pack | 30.1 | 43.4 / 33.6 | 27% |
| the pack | 0.2-0.5, "frozen" (and its retry) | 11.0 / 5.9 | 81-90% |

- The render thread is what is full: it decodes the PNGs, makes the chains and stages RGBA8, and with the pack over the
  cache's 2 GB it lets textures go and uploads them again.
- **Coverage is good:** in the shots nearly every surface is magenta (the sky, the walls, Kratos, the floor): the ids
  hold, and the rule that stops asking for a texture uploaded four times for a change (`churn`) did not keep the
  streamed ones from their pictures here. Left the game's: what the two dumps never saw.

## What a pack needs

1. **Compressed pictures**: DDS with BC1, BC3 or BC7 and their own chain, uploaded as they are: no decode, no chain on
   the CPU, a quarter to an eighth of the memory.
2. **Off the render thread**: pictures read ahead on a worker; the game's own texture is drawn until the picture is
   ready, so a new area costs no stall.
3. **Normal maps**: `rsx_tex_mip_down` weighs the colour by alpha (no dark rim beside a clear texel). For an AG normal
   map the alpha is the normal's x, so the chain made for its picture is skewed. That holds for mods' normal maps
   today. A picture that is a normal map wants a plain average, normalised again, or the DDS's own chain.
4. **The cache's budget** for a pack: a third of the VRAM, at most 2 GB, is too little for one at 4x even compressed.
5. **The tool** (the player's own upscaler, `scripts/modtools.py`):
   - Sorts the dump: colour, AG normal map, alpha cut-out or blend; leaves out masks, flat ones, frame copies and small
     ones.
   - Pads a tiling texture with its own other side before upscaling, so the edges still meet.
   - Normal maps are rebuilt to x, y, z, upscaled, normalised and packed back as AG. Alpha is upscaled on its own.
   - Compresses to BC with chains, and writes a mod (with `aliases.txt` for the game's copies of a texture).
6. **Coverage**: a texture is dumped only when it is drawn, so a pack holds what was played with the dump on. Taking
   every texture out of the WADs and streams with the same ids is a study of its own.
7. The textures stay the player's: the port gives the tools, not textures.

## Not measured

- How an upscaler's output looks: the stand-in is Lanczos, and the look depends on the model.
- The game with a pack in the cinematics and the later levels.
