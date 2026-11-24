# Contrast: a curve that keeps the shadows (issue #4, 2026-11-24)

A player compared Ascension-R 0.3.1 with BilalReloaded's port at the same spot, both with vibrance and contrast at
their maximum: ours was much darker, its shadows crushed. Their screenshots, measured:

| luminance percentile | theirs | theirs through our Contrast Max | ours |
|---|---|---|---|
| p5 | 0.010 | 0.004 | 0.004 |
| p25 | 0.043 | 0.019 | 0.019 |
| p50 | 0.096 | 0.050 | 0.050 |
| p75 | 0.207 | 0.144 | 0.140 |

The pictures under the grade were the same; the difference was our curve. It was a smoothstep on the luminance, its
middle at 0.5, by K (Max 0.65). Most of this game's frame is far below 0.5 (a median near 0.1), so Max scaled the
shadows by 0.39-0.53 (0.05 to 0.022) and the frame lost a third of its brightness: 38% of it near black against 18%.

The curve now goes through P = 0.3, with its lower half weighted by smoothstep(0, P, l): tones above P lighter (by up to
13% at Max), those just below it up to 11% darker, deep shadows as they were (0.05 stays 0.048), black and white kept.
Off, Low to Max and Vibrance are unchanged.

Bench screenshot at Megaera's arena (one run each, bilinear + SMAA and FSR):

| | p5 | p25 | p50 | p90 | mean | near black |
|---|---|---|---|---|---|---|
| Off | 0.012 | 0.054 | 0.152 | 0.558 | 0.247 | 14.1% |
| old Max (simulated on Off) | 0.004 | 0.024 | 0.094 | 0.577 | 0.225 | 29.1% |
| new Max, with Vibrance Max | 0.012 | 0.051 | 0.132 | 0.630 | 0.263 | 14.2% |

The same player's other screenshot, "Contrast Max breaks textures in the shadows", shows patterned garbage on pillars
and wall blocks: texture data, not the grade, which only scales a pixel's own brightness (issues #9 and #34).
