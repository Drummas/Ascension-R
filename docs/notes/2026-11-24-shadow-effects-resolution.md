# Shadow resolution and effects resolution (graphics plan items 1 and 2, 2026-11-24)

Two launcher rows in the Graphics tab, both off by default:

- **Shadow resolution** (`graphics.shadow_resolution` = 1, 2, 4; `D3D12_SHADOW_RES`): shadow maps drawn that many times
  larger, at any internal resolution.
- **Effects resolution** (`graphics.effects_resolution` = game, internal; `D3D12_EFFECTS_RES`): the post chain's targets
  drawn at the internal resolution, by the same factors as the display-size targets.

## How

Both are the internal resolution's mechanism (note 2026-11-08) applied to more targets. `rs_dims` in
`rsx_d3d12_backend.c` replaces `rs_class` and decides a surface's D3D12 size and factors by its guest size:

| guest surface | drawn at |
|---|---|
| the display's size | the internal resolution, as before |
| the display divided by 2, 4, 8 or 16 (640x360 ... 80x45 at 720p), not a float format | with Effects resolution = internal: the display's factors, assigned exactly, so copies between targets (which need equal factors) still match |
| float colour targets at those sizes | the game's size: in this game they are the luminance chain its exposure is measured on (640x360, then 160x180, 40x45, 8x9), sampled with the game's own offsets |
| any other depth surface | Shadow resolution's factor, halved until it fits in 16384 |
| a colour target at a shadow map's offset and size (its colour copy) | the shadow map's factor |
| anything else | the game's size |

The viewport and scissor follow each target's own factors (`rs_target`), and the guest's view of every size is unchanged.
`TS_ON` (internal resolution or Shadow resolution on) now gates WPOS back to guest pixels (`fp_alpha.w`), so a shadow
pass at 720p with 4x shadows is corrected too. A depth surface taken for a shadow map but drawn with a colour target at
another scale logs `[D3D12] depth surface 0x... drawn larger as a shadow map ... is drawn with a colour target ... too`
once: not seen at Megaera's arena, where the only such surface is the shadow map.

The log names what was enlarged: `[D3D12] shadow map 0x01550000 1392x1396 drawn at 5568x5584` and
`[D3D12] effects target 0x02662000 640x360 drawn at 1280x720`, up to 8 lines each.

## Checked

Bench at Megaera's arena, 1440p (internal resolution 2x), bilinear, the game's shadows on. Eight runs: the game's sizes
twice, Shadow 4x alone, Effects internal alone, both four times (once per build), with screenshots at 75 and 95 s; two
more under RenderDoc, the second of which captured a gameplay frame.

- **Shadow maps.** A RenderDoc capture of a gameplay frame: all 278 draws into `0x01550000` are depth-only with 4x
  viewports (702x710 -> 2808x2840, 1386x1396 -> 5544x5584, 682x892 -> 2728x3568), and the 768 scene draws that read it
  read the 5544x5584 surface. The backend's emulated depth compare takes its texel size from the surface
  (`GetDimensions`), so its 2x2 filter is 4x finer too. The saved map is filled over its whole size.
- **What it looks like here.** Very little changes in this scene: its shadows are soft, backlit, and the vase's and the
  debris's shadows are the same at 1x and 4x. Mean difference to the game's sizes 2.5-2.8 (out of 255), against
  0.7-0.9 between two runs of the same settings; most of it is animation. The gain should show on hard shadows close to
  the camera (bars, railings, foliage) and in motion (less crawling on shadow edges); the #34 corridor's bar shadows
  are the place to look (`play-34.bat hd` against `hd0`).
- **Effects.** The capture shows 640x360 -> 1280x720, 320x180 -> 640x360, 160x90 -> 320x180, 80x45 -> 160x90; the FP16
  luminance chain at the game's size. No `[blit-rt] ... not copied` and no `[ds-convert] ... not refreshed`. The glow
  around the gate is a little softer. The frame is 1-3% darker on bright surfaces (mean 53.5 -> 52.0; floor -2.7,
  sky -1.5): the glow adds a little less light. Keeping the luminance chain at the game's size did not change this,
  so it is the bloom chain's own sampling, whose offsets are the game's 640-wide texels.
- **Cost.** The arena runs at 53.1-53.9 fps in every configuration (the frame is CPU-bound here); the 3D engine's use
  58-61% in all three of base, shadow-only and effects-only, within noise. Memory: a 4x shadow map of 1392x1396 is
  5568x5584 D24S8, 124 MB (8 MB at 1x); the process's private bytes 7194 -> 7380 MB with both on.

## Not done

- The game's own shadow filter: where it blurs shadows by a fixed amount in its own texels, a larger map cannot make
  the edge sharper, only cleaner.
- Effects at the internal resolution keep the game's sample offsets, so the glow is the game's width with more samples
  between; matching its brightness exactly would mean scaling those offsets in the programs.
- Bench at 4K internal, where the GPU becomes the limit, for a real cost in milliseconds.
