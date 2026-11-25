# Graphics upgrades: what could make the picture richer

Written 2026-11-24, at port `1b4b5f5`, fork `be0a6c5d`. No code changed. A list to work from later, ordered by what a
player sees for the work it takes. Everything here builds on what the renderer already has: the scene's depth, the
title's camera (`rsx_fsr3_pose_get`), the point before the HUD is drawn (`fg_marker`), and the post pass at the end.

**In short**
- Start with 1 and 2: the targets still drawn at the PS3's size are what looks worst at 1440p and 4K, both are the same
  kind of work (scaling targets the internal resolution leaves alone), and neither needs the game's code read.
- Then 3 (ambient occlusion) for depth, and 4 (HDR) for players with HDR displays.
- 7 is small and can go in any time.

| # | what | what the player sees | size | needs the game's code read? |
|---|---|---|---|---|
| 1 | shadow maps at 2x or 4x: **done** (Shadow resolution) | sharp shadows instead of blocky, blurred ones; most of all outdoors | medium | no |
| 2 | bloom, blur and depth of field at the internal resolution: **done** (Effects resolution) | smooth glow and light, no shimmer on bright edges at high resolutions | medium | no |
| 3 | ambient occlusion (GTAO or SSAO): **done** (Ambient occlusion) | corners, gaps and where things meet the floor darken softly: a deeper, more solid scene | medium to large | no |
| 4 | HDR output (HDR10, the SDR picture expanded, as Windows' AutoHDR does): **done** (HDR) | fire, lava and sky glow on an HDR display while the shadows stay deep | medium | no |
| 5 | field of view setting | a wider view, most of all at 21:9 and 32:9; asked for in #39 (camera at the Aegaeon fight) | medium to large | yes: the camera's field of view |
| 6 | level of detail kept further away | far models and detail no longer drop early | large | yes: the LOD distances |
| 7 | debanding (dither) at the output, and CAS sharpening for DLSS and bilinear | no banding in dark fog and skies; a crisper picture without FSR | small | no |
| 8 | HD texture pack tools: dump, upscale, back into the mods folder | sharper textures; the players' own, made from their own game | small to medium | no |

## 1. Shadow maps at a higher resolution

**Done 2026-11-24** as `graphics.shadow_resolution`: see [the note](2026-11-24-shadow-effects-resolution.md) for what
was measured. In the arena the visible change is small: the game's shadows there are soft.

`graphics.render_scale` draws the scene's targets larger, but leaves the shadow maps at the size the game asks for
(the launcher and `docs/FEATURES.md` say so). At 1440p and 4K a shadow's edge is then a few large texels.

- Find the shadow map targets: depth-only surfaces the scene samples with a depth comparison
  (the `0x90`-`0x93` depth formats read as textures, `tex_dz`).
- Draw them at 2x or 4x: viewport, scissor and the surface's size scaled as the internal resolution does for colour
  targets; the shadow lookups need no change, as they sample in UV.
- A setting `graphics.shadow_scale` = 1, 2, 4, with the VRAM cost in its text (a 1024x1024 D24S8 map is 4 MB, 64 MB at
  4x).
- Watch: the game's shadow cascades may share one atlas; a map the CPU or an SPU reads back must stay at the game's
  size, as other targets do now.

## 2. Bloom, blur and depth of field at the internal resolution

**Done 2026-11-24** as `graphics.effects_resolution`, the regions the game measures its exposure in kept at the game's
size (twins): see [the note](2026-11-24-shadow-effects-resolution.md). The frame's brightness matches the game's; at the
arena the depth of field is what changes (the bloom adds nothing there).

The same rule leaves the half- and quarter-size targets of the post chain (`0x02662000`, `0x024A0000`, `0x029F0000`
and the like in a frame capture) at the game's size, so bloom and blur are upscaled from 640x360 at any resolution.

- Scale the post chain's targets by the internal resolution's factor, keeping their ratio to the frame (half stays
  half).
- The blur kernels sample in UV, so they widen with the target and keep their look; a fixed-pixel kernel would
  shrink, so check the bloom's width against the game's before and after.
- With the MLAA path on, the bloom is drawn after MLAA's composite: check both paths.

## 3. Ambient occlusion

**Done 2026-11-25** as `graphics.ambient_occlusion` = off, on, high: an SAO-like obscurance rather than GTAO, at the
HUD's clear from the scene's own depth; see [the note](2026-11-25-ambient-occlusion.md). About 1-2 ms at 4K internal.

A pass after the opaque scene and before the HUD, from the depth the FSR inputs' pass already makes (R32 at the render's
size, 0 near) and the camera's projection.

- GTAO (XeGTAO's approach) at half resolution with a bilateral upsample: about 1-2 ms at 1440p on a mid GPU.
- Applied as a multiply on the scene's colour before the HUD, kept off the sky (depth at the far plane) and weaker in
  fog; the game's own lighting stays as it is.
- A setting `graphics.ambient_occlusion` = off, low, high. Off by default until the picture is judged in many places.
- Watch: transparent things drawn after the depth (water, fire) must not be darkened; the game's own baked AO in
  some places may make it too dark there.

## 4. HDR output

**Done 2026-11-25** as `display.hdr`, `display.hdr_peak`, `display.hdr_paper_white`: see
[the note](2026-11-25-hdr-output.md). Checked by decoding the swap chain's PQ values (no HDR display here); off with
frame generation for now, and the HUD's white is raised with the rest.

- Swap chain in R10G10B10A2 with the HDR10 colour space (`DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020`), only when the
  display reports HDR.
- The game's SDR picture expanded with an inverse tone curve (peak and paper white set by the player, as AutoHDR and
  RTX HDR do), then PQ-encoded in the post pass's last shader; the HUD kept at paper white.
- DLSS frame generation takes HDR10 as it is; FSR frame generation and the port's overlay need checking.
- A setting `display.hdr` = off, on, with peak brightness and paper white.

## 5. Field of view

- Find where the game builds its projection from a field of view (the vertical one is in the camera the FSR inputs
  read: about 36 degrees in play) and add a patch that scales it, as the other title patches do.
- Ultrawide already widens the picture sideways; this is the other axis, and what the #39 tester asked for at the
  Aegaeon fight.
- Watch: cinematics should keep the game's own field of view; culling may need its frustum widened too, or the edges
  pop.

## 6. Level of detail further away

- Find the game's LOD distance table or its scale and add a patch that multiplies it.
- Watch: streaming budgets (the VRAM pool is close to full in places, issues #39 and #42); a larger LOD distance
  loads more.

## 7. Debanding and CAS

- A blue-noise dither of 1/255 in the post pass's last shader: dark gradients stop banding at no visible cost.
- AMD CAS (MIT) after DLSS and bilinear scaling, with the FSR sharpening setting's levels.

## 8. HD texture pack tools

- The mods folder already takes textures by id and dumps them (`mods.dump_textures`, `docs/MODDING.md`).
- A script that takes a dump, runs an upscaler the player chooses (Real-ESRGAN and the like, run by the player), and
  writes the results back as a mod with `aliases.txt`; the textures stay the player's.
