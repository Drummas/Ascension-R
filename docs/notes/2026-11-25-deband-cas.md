# Debanding and CAS sharpening (graphics plan item 7, 2026-11-25)

Two launcher rows in the Graphics tab, both off by default: **Debanding** (`graphics.deband` = off, on; `D3D12_DEBAND`)
and **CAS sharpening** (`graphics.cas` = off, low, medium, high, max; `D3D12_CAS`).

## How

`post_final` in `rsx_d3d12_backend.c`: the picture's last pass at the window's size, after the scaling (and FSR's
upscaler or DLSS) and before the overlay, when either is on. The picture is copied (`s_pf_tmp`), then one full-screen
pass draws it back:

- **CAS**: AMD FidelityFX CAS's method. A 3x3 neighbourhood's soft minimum and maximum (the cross's plus the whole
  square's) set an amount, the square root of how far the pixel's range is from clipping, and the pixel is pushed away
  from its four neighbours by it: `(sum of the cross * w + centre) / (1 + 4w)`, `w = amount * -1 / lerp(8, 5,
  sharpness)`. Sharpness: low 0.2, medium 0.4, high 0.6, max 1. Only where the scaling sharpened nothing itself:
  bilinear, sharp bilinear, NVIDIA DLSS, FSR 1 without upscaling. FSR 1's RCAS and FSR's upscaler keep FSR sharpening
  (`graphics.sharpening`), which has its own default of high, so CAS is a row of its own and stays off by default.
- **Debanding**: four samples at a random angle and a random distance of up to 16 pixels at 1080p (scaled with the
  window's height), the four at right angles. Where all four are within 1.5/255 of the pixel, per channel, their mean
  takes its place (a flat area: the step was banding); then a triangular dither of one 8-bit step. Past the threshold
  (edges, texture) the pixel stays as it was, CAS's result included, so banding is not sharpened. The noise is fixed
  per pixel (interleaved gradient noise), so it does not crawl.
- Off with frame generation: it finds the HUD by what differs between the picture and the one without the HUD, and
  this pass would make every pixel differ.

## Checked

Megaera's arena, 1080p window, internal resolution 2x, bilinear, output screenshots (three runs: neither, deband, CAS
high):

- The sky above the walls, contrast stretched: blotches with hard edges without it, a smooth gradient with a fine grain
  with it; the walls' and spears' edges as they were.
- CAS high: the stone's grain and the cage's bars crisper, no ringing seen.
- 59.9 fps in all three: a copy and one pass at the window's size.

## Not done

- The game's own 8-bit buffers band before this pass sees them: what is smoothed here is what reaches the screen.
- With frame generation: would need the same pass on the picture without the HUD.
