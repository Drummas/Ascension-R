# Black squares and triangles on the floor under Megaera (2026-11-25)

Reported by the user: at the start of a new game, as Megaera whips Kratos on the round platform, the floor showed black
squares or triangles and the shadows looked wrong. Seen here in every run that reached the moment, with the dynamic
shadows on: a black rectangle in front of Megaera with the game's shadow size, black triangles with Shadow resolution
4x. With the shadows off (Smooth) there is nothing to see.

## Reaching it

`build/issues/megaera/newgame.py`: New Game on the third, empty profile of a fresh copy of the bench saves (Square skips
the opening movie, Cross on Single Player, Down twice, Cross, then Cross for the profile and the difficulty), and
screenshots every second or half second; the moment is about 160 to 165 s after the movie closes, and it moves by a
second or so between runs. `RENDERDOC_ON_SHOT=1` (new, ps3recomp) makes each screenshot also take a RenderDoc capture of
the next frame; with RenderDoc loaded the game runs several times slower, so the captures were taken from 163 s on.

## What the capture showed

- The black is in the screen-space shadow mask (`0x01D90000`): the full-screen draws that fill it, one per depth slice
  (depth bounds), write 0 there. Those draws are the same program with the same constants on the good pixels and the
  bad ones.
- They compare against the depth surface `0x01550000` (1408x1406), which holds the shadow maps of several lights in
  turn within one frame: it is cleared five times, each clear a corner of it (1408x1406, 622x1406, 1408x1256,
  622x1256, ...), and each light's map is drawn in that corner.
- A light's map is read as a texture the size of its corner (622 wide, say), its sampler clamping to the border, a white
  one: outside the map is lit. This backend reads the corner out of the whole surface, its coordinate scaled to the
  corner (`fp_tcscale[u].xy`, note 2026-10-28's region scale), so the sampler's border was at the surface's edge, and a
  lookup past the corner read whatever another light had drawn there: a block of the wrong depth, in shadow.

## The fix

ps3recomp: the depth comparison of the run-time programs (`_rsx_shadow_dN`, `rsx_fp_decompiler.c`) takes each tap
through `_rsx_shadow_tapN`: when the unit's texture is a corner of a larger surface (its scale below 1), a tap outside
the corner reads the guest sampler's border red (bit 8 of the unit's state, the red in bits 10-17) for BORDER on either
axis, or is clamped to the corner's last texel (bit 9) for the other modes. `fp_dyn_state` sets the bits.
`RSX_SHADOW_REGION=0` reads past the corner as before. The programs compiled in full (RSX_FP_DYNAMIC off) are not
changed.

## Checked

i5-12400F, RX 6700 XT, 1080p, shadows on:

- Before: the black rectangle at 1x (one run), black triangles at 4x (three runs, one of them with
  `RSX_SHADOW_REGION=0` on the fixed build).
- After: four runs through the moment (1x and 4x, two of them a screenshot every half second): the floor clean, Megaera's
  and Kratos's own shadows where they fall.
- The bench route (the gate, Profile 1's checkpoint) with and without the fix: the same picture (1% of pixels differ by
  more than a tenth, the pose and the enemy), 50.7 against 51.4 flips/s, one run each.
- The shadow programs' text changed, so their pixel shaders are built again once.

## Not this

The same scene's Dodge tutorial looked banded, with a lighter rectangle under the tutorial's panel, in screenshots
viewed scaled down. At full size the sky and the dark corners are smooth (the banding was the scaled-down viewing), and
the rectangle is the panel's own shade: a quad from the panel down to about two thirds of the screen, a 32x256 gradient
that fades downwards, its left edge faded by the vertex's third texture coordinate (from 0 to 1 over the left eighth of
the screen), as the game draws it. RenderDoc and the port's own dumps of the frame agree.
