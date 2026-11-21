# AMD FSR 4.1 and 3.1 (2026-11-22)

## What the FSR API picks

The port creates its upscaler through the FSR API with no version override, so the API takes the newest upscaler the GPU
and its driver have. SDK 2.4.0's DLLs (the upscaler DLL is 4.1.2.4555) hold FSR 4.1.2, 3.1.6 and 2.3.4, and 4.1.2 runs on
AMD Radeon RX 6000 and newer; the RX 6000 needs driver 26.10.1 or later. On an RX 6700 XT with a driver of 2026-11-17:

    [fsr3] upscaler versions on this GPU: 4.1.2, 3.1.6, 2.3.4
    [fsr3] upscaler: 4.1.2
    [fsr3] frame generation: 3.1.6

Frame generation stays 3.1.6 and its swap chain 3.1.7 there: their 4.x need an RX 9000. Release 0.2.0 ships the same
upscaler DLL (same SHA-256), so it already ran 4.1.2 on those cards while the launcher said "AMD FSR 3.1". Other GPUs
get 3.1.6.

## The setting

`graphics.fsr_version` (FSR version in the Graphics tab, under Scaling): `auto` by default, or the start of a version.
`3.1` lists the versions the GPU has (`ffxQueryDescGetVersions` with the device) and pins the newest 3.1 by its id
(`ffxOverrideVersion` on the create chain), which the log shows as `[fsr3] upscaler: 3.1.6, as asked (3.1)`. A version
the GPU does not have, or a pinned context that fails, falls back to the API's own choice. `D3D12_FSR_VERSION` sets it
from the environment.

The version in use is on the stats panel (`Upscaler: FSR 4.1.2 + FG 3.1.6`), on the launcher's ready check (`Upscaling:
AMD FSR 4.1.2`, from the newest session log that made an upscaler with the same setting) and under each session in a
problem report (`AMD FSR: upscaler 4.1.2 (the newest the GPU takes), frame generation 3.1.6`).

## 4.1.2 against 3.1.6

Two sessions on the bench route (Profile 1's checkpoint), one with `graphics.fsr_version=3.1` and one with `auto`, on an
RX 6700 XT and an i5-12400F: 1080p from 1080p, sharpening high, frame generation on at 120 Hz, `RSX_CENSUS=5`, the stats
panel, screenshots of the output after FSR. The census's "the rest" is the GPU time after the frame's draws: the
upscaler, the grade, the HUD and frame generation's prepare.

| | 3.1.6 | 4.1.2 |
|---|---|---|
| "the rest" in play, 5 s windows | 2.24 to 2.63 ms, mean 2.43 (5) | 3.42 to 3.98 ms, mean 3.66 (6) |
| standing at the same spot, stats panel | 37 fps, GPU 49% | 38 fps, GPU 50% |

So 4.1.2 costs about 1.2 ms of GPU time a frame more at 1080p; AMD gives 2.46 ms for the whole pass on this card at
1440p in performance mode. The spot was paced by the CPU (the PPU thread at 84 to 100%), so the frame rate did not move;
where the GPU sets the pace, expect that 1.2 ms off each frame.

In the screenshots 4.1.2 draws silhouettes, thin lines and strands with far less stair-stepping, in motion too. 3.1.6
keeps textures a little sharper (the arch's carving, the stone). With sharpening high, 4.1.2 is the softer of the two,
so high stays the default for both.

## For the release notes

AMD FSR scaling is FSR 4.1 on AMD Radeon RX 6000 and newer (driver 26.10.1 or later on the RX 6000) and FSR 3.1 on
other cards; 0.2.0 already ran 4.1 there. The launcher names the version in use, and FSR version: 3.1 pins the older,
lighter one.
