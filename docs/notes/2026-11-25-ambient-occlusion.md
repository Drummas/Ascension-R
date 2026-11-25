# Ambient occlusion (graphics plan item 3, 2026-11-25)

A launcher row in the Graphics tab, off by default: **Ambient occlusion** (`graphics.ambient_occlusion` = off, on,
high; `D3D12_AO`). Soft shade where things meet and in corners and gaps, worked out from the scene's depth.

## How

`ao_draw` in `rsx_d3d12_backend.c`, two full-screen passes:

1. **The occlusion**, into an R8 target of its own: at half the render's size with 8 samples (on) or at its size with
   16 (high). Each pixel's position goes back to the world through the inverse of the title's world-to-clip matrix, the
   camera FSR's inputs take (`s_fg.cam`, `z_scale`/`z_offset`, the same unprojection as FSR's inputs' pass). Its
   normal comes from the nearer of each pair of neighbours, turned toward the camera (where the planes of the
   matrix's rows 0, 1 and 3 meet). Then samples on a disc of 1.2 world units around it (the camera's near plane is at
   0.25 and its far one at 625: the units are about a metre), in UV from the clip-space scale of the matrix's rows,
   on a golden-angle spiral turned by a 4x4 Bayer pattern: what stands above the surface within the radius darkens it
   (an Alchemy/SAO-like obscurance, 2.4 strong). Faded out between 25 and 50 units of view depth (the title's fog),
   none on the sky.
2. **The blur into the colour**: 4x4 taps of the occlusion around each pixel, weighted by how close their view depth is
   (within 4%), which takes out the Bayer pattern; the colour multiplied by it, its alpha kept.

Where: the scene is whole when the title clears depth on a display surface for its HUD (`fg_marker`). God of War:
Ascension draws its scene with depth 0x11B0000 and clears 0x2B20000 for the HUD, so the occlusion takes the scene's own
depth there, and goes on before frame generation's copies take the picture (so FSR's upscaler and frame generation
see it). A frame with no HUD's clear gets it after the frame is composited, before a screenshot or the scaling. The
camera is the frame's first draw through it at the display's size; it is now taken each frame with frame generation
and the upscaler off too (`fg_frame` used to return before its reset then, which left the first camera for good and
the occlusion drawn once). Off with an ultrawide picture, whose projection is not the title's.

`D3D12_AO_DEBUG` set logs where it was drawn (`[ao-dbg] at the HUD's clear`, `at the frame's end`); 1 shows the
occlusion alone, 2 the view depth (red bands of 10 units, green 0 to 100).

## Checked

Megaera's arena, the bench route: nine runs at 1440p while it was built (most with a debug view), three for the cost at
4K, one with AMD FSR scaling.

- The occlusion alone shows the scene's shapes as they are: the gate, the walls' bases, the pillars, Kratos, the
  vases, flat surfaces white, no noise. With the colour: contact shade under the vases and the fallen blocks, the
  folds of Kratos' back, arms and kilt deeper, nothing over the sky. Light on purpose: the game's own lighting has
  shade of its own.
- Its passes in the log: `at the HUD's clear` from the first frames of play on, `at the frame's end` for frames with
  no HUD's clear.
- Cost at 4K internal (render scale 3, bilinear; one run each, `RSX_CENSUS=5` GPU timestamps, mean of the 21 reports
  of play):

  | | GPU a frame | fps (median) |
  |---|---|---|
  | off | 12.02 ms | 49.9 |
  | on | 13.05 ms (+1.03) | 47.4 |
  | high | 14.14 ms (+2.12) | 46.9 |

  At 1440p (bilinear, no census) 53.5 fps off and 52.5 high.
- With AMD FSR scaling (FSR 4.1.2 on this GPU, 1440p internal to a 1080p window, on): drawn at the HUD's clear as
  without it, so the upscaler takes the shaded scene; the picture clean, 50.9 fps.

## Not done

- Transparent things drawn after the scene's depth (fire, water, particles) take the shade of what is behind them.
- Ultrawide: the occlusion would need the widened projection.
- The blur keeps to depth only; thin things against a far background can keep a faint edge.

## Later the same day: On drew stripes

On (half the render's size) drew horizontal stripes on floors seen at a low angle: each half-size pixel's depth was read
at the edge of two of the render's pixels and put half a pixel away. Points are now taken at the middle of the pixel
their depth comes from. Found and checked with the Balanced preset (note 2026-11-25-presets.md).
