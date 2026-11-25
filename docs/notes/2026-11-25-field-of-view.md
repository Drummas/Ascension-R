# Field of view (graphics plan item 5, 2026-11-25)

A launcher row in the Graphics tab: **Field of view** (`graphics.fov` = 0.8 to 1.4, the game's 1; `GOWA_FOV`), how wide
the view is in play against the game's. 80% and 90% bring the view in (what the #39 tester asked for at the Aegaeon
fight, where the camera pulls far back); 110% to 140% show more around Kratos.

## How

The ultrawide work (note 2026-11-10) found where a perspective camera's field of view becomes its half-width:
`func_003B0380` at `0x003B05A4`, f1 the tangent, about to go to `+0x3C0` of the camera, and the title's frustum comes
from it, so culling follows. `gowa_wide_fov` (`port/ultrawide.cpp`) is already called there; it now also multiplies the
tangent by the setting, for the play camera only.

A probe (`GOWA_FOV_PROBE=1`, a line a second with each camera, its lens object at `+0x47C`, its angle and how often it
was worked out, and how often the camera controller ran) on the bench route and its opening:

| | the camera worked out twice a frame (and the static one at `0x00994570`, same lens) | two others, one lens | the camera controller (`func_00314780`) |
|---|---|---|---|
| loading | 41.6-55 degrees (horizontal) | 54.4 | not run |
| play at Megaera's arena | 73.1 | 53.9 | ~120 times a second |

So play is when the controller has run in the last 0.15 s (`gowa_wide_framing` keeps the time), and the play cameras
are those that share the lens of the camera worked out most often over the last half second. The two others keep a
fixed 54 degrees through everything (the menus' and the HUD's, by their constancy). The factor eases over 0.4 s between
1 and the setting at a change. It multiplies with the ultrawide ratio.

## Checked

The bench route's opening, played through (Megaera arriving at the gate, then play): at 130% the factor is 1.00 while
the controller does not run and 1.30 once it does, the two fixed cameras untouched. Screenshots at +15 to +40 s: more of
the arena at the sides and above (the mechanisms left and right, the sky), Kratos smaller, nothing missing at the edges
(the title's culling goes by the same numbers). The opening is drawn through the play camera, so it widens too.

## Not checked

- A cinematic drawn through its own animated camera: the controller should not run there (it did not during loading),
  but none was reached on the automated route. To look at in play.
- The camera controller still frames Kratos as at the game's view: at 80% he can be closer to the edges.
- The Aegaeon fight itself.
