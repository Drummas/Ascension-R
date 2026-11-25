# The Ultra preset, in Faithful's place (2026-11-25)

Faithful ("everything drawn as on the PS3") had every game patch off, MLAA included. MLAA's work is a copy of the frame
in main memory that this port never shows (note 2026-11-23-bloom-spu-mlaa.md), so Faithful paid about 5% for nothing,
and it left the picture at whatever the Graphics tab had. Ultra takes its place as the most the port can draw.

## What a preset sets now

A preset was the game patches it switches on. It now also gives some settings a value (`Preset.set` in
`port/launcher.cpp`); `preset_now` matches both, so a preset shows as chosen only while all of them hold, and anything
else is "Custom setup".

| | Smooth | Balanced | Ultra |
|---|---|---|---|
| patches on | Disable MLAA, Disable motion blur, Disable shadows | Disable MLAA, Disable motion blur | Disable MLAA (its picture is never shown), Disable mesh trimming (keeps the thin triangles above 720p) |
| internal resolution, scaling | left as set | left as set | the window's size, bilinear |
| frame generation | left as set | left as set | off |
| anti-aliasing, filtering | left as set | left as set | SMAA, 16x |
| shadow resolution, effects resolution, ambient occlusion | 1, game, off | 1, game, off | 4, internal, high |
| debanding, CAS | left as set | left as set | on, low |

Ultra does not use AMD FSR or frame generation: both take the game's frame order without MLAA, where the bloom and the
motion blur never reach the picture. Colour vibrance, contrast, field of view, HDR and the display settings stay the
player's. `recomplauncher.json`'s preset choice sets the same values.

## Measured

i5-12400F, RX 6700 XT, 1080p borderless, the bench route (`gowa.py bench`, the gate fight from Profile 1's checkpoint),
two runs each (the route check called the first of each failed and ran it again; both reached the fight):

| | median flips/s | GPU busy |
|---|---|---|
| Smooth with this PC's settings (AMD FSR from 1.5x) | 56.5, 59.7 | 70% |
| Ultra | 40.4, 37.9 | 69% |

The GPU is as busy in both: the extras (4x shadow maps, effects at full size, high ambient occlusion) are not what costs
here. The game's own dynamic shadows and motion blur, which Smooth turns off, are CPU and SPU work, and that is where
the frames go. On a weaker GPU or at 1440p and 4K the extras add their own (note 2026-11-24, 2026-11-25: about 0.6, 0.6
and 2 ms at 4K).

Changing a setting that shapes the shaders (shadow resolution among them) shows "Pixel shaders partly built" on the
ready check until **Build** or the first session builds the rest, as before.
