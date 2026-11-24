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
| float colour targets at those sizes | the game's size: in this game they are steps of the exposure chain (below) |
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

## The exposure chain: regions at the game's size (twins)

The first version made the frame 1-3% darker with Effects resolution on (mean 53.5 -> 52.0 of 255; floor -2.7, sky
-1.5, in proportion to brightness). Two RenderDoc captures of the same gameplay frame, game's size against internal,
with every post pass's output averaged, showed every bloom and depth of field pass within 0.3% and the final frame 0.3%
brighter: the chain loses no light. What differed was the exposure. The game measures the frame's luminance in the
first 9 of its 33 post passes: from the scene into 640x360, then into 160x180, 40x45 and 8x9 **corners** of the same RGBA8
targets its bloom (`0x024A0000`, 640x360) and depth of field (`0x029F0000`, 320x180) use whole, each read back as
Y16_X16 through `y16_convert` (point-sampled on texel edges), alternating with FP16 targets of those sizes; the PPU
takes the exposure from the 8x9 result. Drawn at twice the size, each corner pixel became four computed a quarter
texel off, and the 8x9 result came out 2.2% low.

With the two targets kept at the game's size (a test switch), the frame matched (53.3 against 53.5, noise 0.2). But
that keeps the bloom's last level and the depth of field's first at 640x360 and 320x180, which is most of what the
option is for. So each such target now has a **twin** at the game's size (`rt_sub_draw`): a draw into a region of a
post-chain target drawn larger (its viewport smaller than the surface; not a clear, one colour target, no depth
surface) goes to the twin, 1:1, and what reads the target (`y16_convert`, the draw's own texture window) reads the
twin until a draw covers the target again. The twin has its own RTV and SRV slots, so commands recorded before it was
drawn keep reading the target. With it, Effects resolution on: 53.4 and 53.3 against 53.5 and 53.3 at 75 and 95 s,
both twins made (`[D3D12] effects target 0x024A0000 640x360: its regions drawn at the game's size`), the same four
`[blit-rt]` lines as the game's sizes, no warnings. The background seen through the arena's gate, blurred by the depth
of field, has smooth edges where the game's size draws it in blocks.

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
  steps of the exposure chain at the game's size. No `[blit-rt] ... not copied` and no `[ds-convert] ... not
  refreshed`. In this frame the bloom chain ends in black, so it adds nothing at the arena: what changes is the depth
  of field, smoother on far things. Brightness: see the exposure chain above.
- **Cost at 1440p.** The arena runs at 53.1-53.9 fps in every configuration (the frame is CPU-bound here); the 3D
  engine's use 58-61% in all three of base, shadow-only and effects-only, within noise. Memory: a 4x shadow map of
  1392x1396 is 5568x5584 D24S8, 124 MB (8 MB at 1x); the process's private bytes 7194 -> 7380 MB with both on.
- **Cost at 4K internal** (render scale 3, 3840x2160; four runs, one per option, `RSX_CENSUS=5` GPU timestamps, the
  mean of the 21 reports of the arena's play, about 105 s each):

  | | GPU a frame | against the game's sizes | fps (median) |
  |---|---|---|---|
  | the game's sizes | 10.93 ms | | 52.9 |
  | Shadow resolution 2x | 11.37 ms | +0.44 ms | 53.4 |
  | Shadow resolution 4x | 11.57 ms | +0.64 ms | 52.4 |
  | Effects resolution internal | 11.53 ms | +0.60 ms | 52.8 |

  One run each, and the reports of two runs at the same moment differ by up to 1 ms, so these are within about
  0.3 ms. Still CPU-bound at 4K on an RX 6700 XT: the GPU is busy ~11 of each ~19 ms. The frame's brightness at 4K
  with Effects internal: 55.6 against 55.5.

## Not done

- The game's own shadow filter: where it blurs shadows by a fixed amount in its own texels, a larger map cannot make
  the edge sharper, only cleaner.
- Effects at the internal resolution keep the game's sample offsets, so a blur is the game's width with more samples
  between. The captures show the same light in every pass, so this changes the look of a blur, not its brightness.
- A scene where the bloom is on, to look at it: the arena's is black.
