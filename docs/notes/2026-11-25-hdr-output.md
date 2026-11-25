# HDR output (graphics plan item 4, 2026-11-25)

Three launcher rows in the Display tab: **HDR** (`display.hdr` = off, on; `D3D12_HDR`), **HDR peak brightness**
(`display.hdr_peak` = auto, 400 to 2000 nits; `D3D12_HDR_PEAK`) and **HDR paper white** (`display.hdr_paper_white` =
100 to 300 nits, 200 by default; `D3D12_HDR_PAPER`). Off by default.

## How

- `hdr_start`, after the swap chain is made: `GetContainingOutput` and `IDXGIOutput6::GetDesc1` say whether Windows has
  HDR on for the window's display (its colour space is `DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020`) and its peak
  (`MaxLuminance`). The log says both on every start: `[D3D12] display: HDR on in Windows, 1015 nits at most as it
  reports`. With the setting on and HDR on there, the swap chain's buffers become `R10G10B10A2_UNORM` (`ResizeBuffers`
  before they are first taken) and its colour space HDR10 (`CheckColorSpaceSupport`, `SetColorSpace1`). Off, with its
  reason logged, where Windows has HDR off or the swap chain refuses it, and with frame generation (its swap chain is
  FSR's or Streamline's). Peak auto: what the display reports, 400 to 2000, 1000 where it reports nothing.
- `bb_get`: with HDR, the swap chain's buffers go to `s_hdr_swap[]` and `backbuffers[]` become R8G8B8A8 targets of
  the same size. Every pass that drew into the swap chain draws into those as before (the scaling, FSR's upscaler,
  SMAA, the overlay), and a screenshot of the output takes them: screenshots stay SDR. `bb_resize` makes both again.
- `hdr_encode`, the frame's last pass before the present: the SDR picture to linear (gamma 2.2, as a PC display shows
  it), highlights raised: above a luminance of 0.5 by a factor that grows with the square of the way to white, up to
  peak / paper white at white, so white reaches the peak and everything below 0.5 stays where it was; times paper
  white, BT.709 to BT.2020, PQ.

## Checked

This PC's display has no HDR (`HDR off in Windows, 0 nits`), so the picture itself was not seen. `D3D12_HDR_FORCE=1`
makes the HDR10 swap chain anyway, for a test. A RenderDoc capture of a frame of play at 1440p with peak 1000 and paper
white 200: the swap chain's buffer R10G10B10A2 1920x1080, the SDR picture beside it, PQ decoded back to nits:

| SDR (green) | expected | in the buffer |
|---|---|---|
| 0.043 (dark) | 0.2 nits | 0.2 |
| 0.271 | 11.3 | 11.0 |
| 0.498 | 43.2 | 42.6 |
| 0.686 | 87.4 | 88.3 |
| 0.926 (Y 0.844, highlight) | 489 | 490 |
| 0.992 (Y 0.974, near white) | 903 | 897 |

The small differences are BT.2020's mix of the channels. A run with HDR forced, AMD FSR scaling (4.1.2), ambient
occlusion and the overlay on went through without an error, its output screenshot the SDR picture with the overlay;
59.9 fps against 59.9 with the same settings and HDR off. The game with HDR off is as before (`bb_get` takes the swap
chain's buffers as it did).

## Not done

- The HUD, menus and the overlay are part of the same picture: their white is raised to the peak like the game's
  highlights, as with Windows' Auto HDR. Lower the peak if they are too bright. Keeping them at paper white would mean
  the picture without its HUD (the HUD's clear, as ambient occlusion uses it) carried through to the end.
- Frame generation with HDR: FSR's and Streamline's swap chains would need HDR formats of their own.
- Seen on an HDR display: not yet, here.
