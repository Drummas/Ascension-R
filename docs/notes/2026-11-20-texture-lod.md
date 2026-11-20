# Textures drawn from levels the title keeps out (2026-11-20)

Issue #9, on 0.1.0-alpha.15 in Sparta's prison (the HRTN levels): walls striped, dotted and blocky, a floor in red and
green bands, and in the palace illusion Kratos's skin a flat pale yellow, "flickering in and out of appearance, mostly
out" (a second player at the same place). The report's log has nothing else: no `[vram]` line, no draw overflow, no
texture torn while it was read in the level.

## The cause

- `vp_sampler` keyed a guest sampler state on TEXTURE_CONTROL0's anisotropy alone (`ctrl0 & 0x70`, since 2026-10-24).
  `rsx_sampler_desc` reads the minimum [30:19] and maximum [18:7] level of detail from that key (since 2026-10-28,
  "upload texture mip chains, and keep to the LOD clamps"), so both were always 0: every texture was sampled at
  level 0, and the chains were uploaded and never read.
- The game streams its textures. A texture whose top levels are not loaded, or were dropped for room, is bound whole,
  with a minimum level of detail that keeps the GPU to the levels it has. When the top levels arrive, the minimum goes
  down a little every frame: a fade. The port read level 0 all the same, and drew whatever was in that memory.
- The parasites' fight, replayed for 150 s with a probe (not kept): 54.8 M texture binds, 39.5 M of them with a
  mipmapped min filter. 27.2% of those let levels past 0 be read; 0.10% (40,282) had a minimum above 0, at values such
  as 1.70, 1.64, 1.58, 1.52, 1.45 on one 1024x1024 texture in turn. There the fades are short. In a place as full as
  Sparta's prison, textures wait longer for their top levels and the video memory manager drops them more often.
- The same fits the striped block in Kirra on 0.1.0-alpha.11 (#9): that texture had only its levels from 256x256 down
  in memory.

## The fix

- The maximum goes into the sampler's key, for the mipmapped min filters (3-6). The minimum goes into the draw's view,
  as `ResourceMinLODClamp`, within the levels the texture's resource has (`vp_unit_lod`, carried above bit 8 of the
  view's shape word, so the view cache and the window sharing tell views apart by it).
- The minimum in the sampler's key was tried first. The fades give it any value: the fight made 1,951 samplers in
  135 s, against the 2,048 a D3D12 sampler heap holds. Taken up to an eighth of a level, it still made 295 by 140 s,
  and climbing. With the maximum alone, 43.
- Samplers are found through a hash table instead of a walk over all of them, and a full heap says so once in the log.
- `RSX_TEX_LOD=0` samples level 0 only, as before.

## Checked

On an i5-12400F with a Radeon RX 6700 XT:

- Since 2026-10-28 the uploaded chains had never been sampled, so first a test build with every sampler's bias raised
  by 3 levels, then one with every view's minimum forced to 3: the bench route's cinematic and the fight replay came
  out blurred, with nothing garbled.
- The cinematic at 1280x720, render scale 1, anisotropy 16, against `RSX_TEX_LOD=0`: the same picture, distant floors
  a little smoother.
- The fight replay, VSync and frame generation off, one run each: flips/s in 10 s windows the same. In the fight
  (70-110 s) 53.4 to 57.0, against 49.6 to 59.5 with `RSX_TEX_LOD=0`; the load at 40 s 36.8 against 37.3; elsewhere
  53.6 to 60 in both.

## Not checked

- Sparta's prison itself: there is no save that far here. The reporter's place is the test.
