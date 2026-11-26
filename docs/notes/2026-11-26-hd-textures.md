# A pack of upscaled textures: DDS, pictures read ahead, normal maps' chains, room in the cache (2026-11-26)

Steps 1-4 of [what a pack needs](2026-11-26-texture-upscale-review.md). That review's stand-in pack (837 pictures
from two dumps at 2x, the colour ones tinted magenta) brought the bench route from 30 flips a second to 0.2-0.5.

## What changed

- **DDS pictures** (`port/textures.cpp`, ps3recomp `rsx_tex_replace.h`, the D3D12 backend). `<id>.dds` beside or in
  place of `<id>.png`, and in `aliases.txt`; in one mod a DDS wins over a PNG of the same id. BC1 (`DXT1`), BC2
  (`DXT2`/`DXT3`), BC3 (`DXT4`/`DXT5`) and BC7 (DX10, DXGI 97-99), with the levels the file holds, uploaded as they
  are: `rsx_tex_picture` has `form`, `levels` and `data`, the resource is `DXGI_FORMAT_BC*_UNORM` with that chain,
  and nothing is decoded or made on the CPU. Level 0 has to be whole blocks (a multiple of 4 on each side, D3D12's
  rule); a 32-bit RGBA or BGRA DDS is taken as a PNG is. A cube, a volume or an array is refused, and the log says
  why (`[tex] <file>: not a multiple of 4 wide and high...: the game's own texture`). A smaller copy of the texture
  (`texture_copies.inc`) takes the chain from the level of about its size. The backend checks a picture against its
  texture's format (a BC picture only for one decoded to RGBA) and against the bytes its chain needs
  (`tex_picture_fits`). The shared-picture table (`VP_TEX_PICS`) holds 4,096, and keys a picture by its format too.
- **Read ahead.** `picture()` answers `RSX_TEXPIC_LATER` for a picture not read yet and queues it for two loader
  threads (below normal priority), which read the file, decode it or take its blocks, keep the texels and call
  `rsx_tex_pictures_ready()`. The backend draws the game's own texture meanwhile and marks the slot (`pic_wait`, the
  id, the count it was asked at); at a later bind, when the count has moved on, it asks the port's `ready(id)` and,
  ready, uploads again with the picture. That upload is not a change of the guest's bytes and does not count toward
  the four that stop a texture from being asked (`churn`). Two textures given the same file at the same size share
  the texels, keyed by the file's content and the size (`read_head`). `GOWA_PICTURE_ASYNC=0`: read when asked.
  Overlays (`.overlay.png`) are read when asked, as before.
- **Normal maps' chains.** `rsx_tex_mip_down` weighs colour by alpha. The game's normal maps are AG (red full, blue
  none, y in green, x in alpha), so the chain the backend made for such a picture leaned to the texels with more x.
  A PNG that looks so (`looks_ag_normal`: red above 230, blue below 30, green and alpha spread) is marked
  `RSX_TEXPIC_PLAIN_CHAIN` and its levels are plain means of each channel (`rsx_tex_mip_down_plain`). A DDS brings
  its own chain.
- **Room in the cache.** At the start the port adds up what the mods' pictures take on the GPU, from each file's
  header (a DDS its blocks and chain, a PNG 4 bytes a texel with a chain), and tells the backend
  (`rsx_tex_set_pictures_bytes`). The texture cache's budget is then the old one (a third of the VRAM, at most 2 GB)
  and that much more, within half the VRAM: `[tex] texture cache: 3186 MB (2048, and the mods' pictures take about
  1074)`. `TEX_CACHE_MB` still sets it outright.
- `mods.cpp` counts `.dds` pictures (a mod of DDS files only was "empty"); `docs/MODDING.md` says all of it.

## Measured

The stand-in pack again, and the same pack as DDS (`build\issues\texup\pack_to_dds.py`: Pillow's BC1 for the colour
ones without alpha, BC3 for the 205 normal maps and 60 with alpha, each with its full chain; 16 s for 837 files). The
bench route, i5-12400F, RX 6700 XT (12 GB), this PC's settings, one run each:

| | bench median (windows) | peak private memory | texture cache |
|---|---|---|---|
| no pack | 48.83 (46.8-50.0) | 7.2 GB | 2048 MB |
| the pack as PNG | 48.42 (48.0-49.6) | 10.5 GB | 6121 MB (the pictures about 6.6 GB as RGBA8) |
| the pack as DDS | 49.27 (47.0-50.2) | 6.9 GB | 3186 MB (about 1.07 GB) |

The day's first run of the route without the pack measured 30.1 (the review's), this one 48.8: the scene and the
settings are the same, so the three above are compared with each other only. Before these changes the PNG pack ran at
0.2-0.5.

- Both packs show on every surface the review's did (magenta), and 1:1 crops of the PNG and the DDS runs at the same
  moment are alike (mean difference 1.9 of 255 over the frame: BC's own loss, and the moment); the normal maps'
  shading on Kratos's back is the same in both.
- The log names the pictures taken with `(its own blocks and chain)` for a DDS.

## Tests

- ps3recomp `tests/test_rsx_tex_replace.c`: a plain level of an AG normal map against the weighted one, BC levels'
  and chains' bytes, the ready count, the pictures' bytes.
- `tests/test_textures.py`: BC1 with its chain, BC7 by DX10's header, a DDS not whole blocks wide refused and named in
  the log, a DDS over a PNG of one id, a copy a quarter the size taking the chain from its level, the first answer
  "later" and the picture once ready (and read when asked with `GOWA_PICTURE_ASYNC=0`), an AG normal map's chain plain
  and a colour picture's not; the earlier tests through the loader.
