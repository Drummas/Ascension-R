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

## Step 5: the pack made from a dump (modtools.py upscale)

`python scripts\modtools.py upscale <dump> <mod>`: each dumped texture sorted (`texture_kind`: colour, alpha, AG
normal map; left out with the reason: linear, one or two channels, under `--min-side`, one colour), the ones with the
same texels made once (the others into `aliases.txt`), padded with their other side when they repeat (`tiles`:
opposite edges as alike as neighbouring texels) or mirrored, upscaled (Lanczos built in, or the player's command
with `{in_dir}`/`{out_dir}` or `{in}`/`{out}`; a bigger result brought to the size), cropped, and written as DDS
(Pillow's BC1, BC3 with alpha, each level a box mean, an AG normal map's channel by channel) or PNG. Normal maps are
rebuilt to x, y, z, upscaled (Lanczos, or the upscaler with `--normals upscaler`), normalised and packed back as AG;
alpha is upscaled apart. Pictures the mod has are not made again (`--force`). Pillow and NumPy are imported only by
this command (the Kit's Python has neither); CI installs them for the tests.

The dump of the first levels (869): 536 colour, 196 normal maps, 47 with alpha made; 49 masks and fonts, 25 small,
12 linear, 4 one-colour left out. 779 DDS in 26 s (16 s of making with 6 processes), 720 MB, about 717 MB on the GPU.
On the bench route (one run): 48.61, the texture cache 2829 MB; 1:1 crops beside the no-pack run at the same moment
show the same shading on Kratos's skin (the normal maps right) and the ground, nothing broken. Lanczos adds no
detail: the look an AI upscaler gives is the player's choice of model, not measured here.

Tests (`tests/test_modtools.py`): a made-up dump (colour, a copy of it, an AG normal map, alpha, one colour, B8,
linear, small): the files and their formats and chains, the alias, mod.ini, the normal map packed back (red full, blue
none, lengths at most 1, its relief kept), a second run making nothing; a player's upscaler that gives 4x for 2x
(brought to the size) with PNGs out and the alpha kept apart; an upscaler that fails; `tiles` on a wave and a ramp.

## With an AI upscaler (realesrgan-ncnn-vulkan)

realesrgan-ncnn-vulkan 20220424 (Real-ESRGAN v0.2.5.0's release, BSD-3) in `C:\tools\realesrgan`, run by
`--upscaler "...realesrgan-ncnn-vulkan.exe -i {in_dir} -o {out_dir} -s 4 -n <model> -f png"`, `--scale 2` (its 4x
brought to 2x). The same four textures with each model, side by side at 1:1 with the source and Lanczos:

| model | grainy stone, patina | edges, ornaments | rock |
|---|---|---|---|
| `realesrgan-x4plus` (its own) | smoothed away, a painted look | sharp, clean | smooth, the grain gone |
| `ultrasharp-4x` (4x-UltraSharp, Upscayl's models) | kept | sharp | sharp, natural |
| `remacri-4x` (Upscayl's models) | kept, harsh | sharp, lines etched | black and white specks |

UltraSharp on the whole dump: 779 pictures in 1,020 s on the RX 6700 XT (the normal maps by Lanczos), 720 MB, about
717 MB on the GPU. Fed to the upscaler 48 at a time now (`--batch`): all at once held every texture's padded texels
until the end.

In the game, one run each, the bench route at a 1920x1080 window and native internal resolution: no pack 48.03,
UltraSharp 49.17. 1:1 crops at the same moments: finer pores and scratches on Kratos's skin, crisper moss on the ground
and grain on the wooden wall; nothing broken, the normal maps' shading the same. At 1280x720 the two are hard to tell
apart: the game's own textures already hold about as many texels as such a frame shows at this distance. The gain is
for 1440p, 4K and close views.
