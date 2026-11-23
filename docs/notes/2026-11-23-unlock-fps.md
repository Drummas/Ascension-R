# Unlock FPS, step 1: the patch and the pace, measured (2026-11-23)

The title steps its world by the real time of each frame, and above 60 frames a second it ran fast. This adds the
title patch `unlock_fps` (scripts/title_patches.json, off by default) and the frame clock's pace for it, behind
switches only, and measures it. The launcher has no row for it yet. The map was the 2026-11-17 study
(docs/notes/2026-11-17-flip-period.md): RPCS3's "Unlock FPS" v2.0 for 1.04, its sites moved to 1.12 and each read
back from this ELF.

## The title's timing

- func_002D01E8 sets the rate once at init: 59.94 from the table at 0x3A52B4, stored to the global 0x83B45C, and
  int(rate + 0.5) to 0x9424A0.
- func_002D0258, each frame: the time since the last frame in periods of 1/rate, clamped to 1-4 periods (the pool
  constants 100 and 400 at 0x2D0248/0x2D024C, x100), and the frame's step in seconds is that over the rate. Mode
  0x9424A8: 0 that variable step, 1-3 the same averaged over 8, 30 or 15 frames, 4 a fixed two periods (the 2.0 at
  0x2D0254); 0x9424D8 forces one period (the 1.0 at 0x2D0250). A frame under 16.7 ms still moved the world 16.7 ms:
  above 60 fps the title ran fast.
- The global is read by 12 functions. Five take the rate as a time base: the time count (func_002CA76C), the frame
  sync (twice), and the video player. The others scale gameplay by it and keep 59.94.

## The patch

Five instruction edits and six data edits:

| Where | Was | Is | Why |
|---|---|---|---|
| 0x3A52B4 | 59.94 | 1000.0 | the rate set at init: periods of 1 ms, int rate 1000 |
| 0x2D024C | 400 | 6667 | the longest step stays 66.7 ms (RPCS3's v2.0 had 100 ms) |
| 0x2D0250 | 1.0 | 16.6834 | the forced one-period step stays 16.7 ms (not in RPCS3's) |
| 0x2D0254 | 2.0 | 33.3667 | mode 4's fixed step stays 33.4 ms (not in RPCS3's) |
| 0x83B45C | -1.0 | 59.94 | the global holds what init would have stored there |
| 0x83948C | 0x447A0000 | the same | checked only: the word the four loads below read |
| 0x2D01F8 | stfs f1,0xb45c(r4) | nop | init no longer stores 1000 to the global |
| 0x2CA79C, 0x2D02E4, 0x2D038C, 0x3F6798 | lfs ...,0xb45c(rN) | lfs ...,0x948c(rN) | the time count, the sync and the video player read 1000.0 |

- 0x83948C is a TOC word, read only through r2 by func_0065BCC0 as a 32-bit value: a link-time constant whose bits
  are 1000.0 as a float. Watched through boot, menus, the opening and the first fight, it stayed so. RPCS3's 1.04
  patch reads the same kind of word.
- The pool constants 0x2D0240-0x2D0254 are func_002D0258's alone (Ghidra's references): patching 1.0 and 2.0 keeps
  the two fixed steps at their old length. The modes and the flag stayed at 0 (the variable step) through boot,
  menus, the opening and the first fight, watched every 0.25 s.
- 0x2D0608, which sets the periods from the global, is reached only from the table at 0x8204E0, the static
  constructors, which run once at start.
- The video player adds 1/rate to its clock each frame and moves it to the audio's when a new audio time comes. With
  the patch it adds 1 ms; the audio keeps it right (below).

`[patches] unlock_fps = on`, `--set patches.unlock_fps=on` or `GOWA_PATCH_UNLOCK_FPS=1` switches it on; the log
says `[patches] Unlock FPS (experimental): on (5 PPU and 0 SPU instruction edits, 24 data bytes)`.

## The pace

The frame clock (port/main.cpp) held a flip to one vblank period after the last (60 a second). With the patch on, it
holds it to 1/fps_limit: `[display] fps_limit` or `GOWA_FPS_LIMIT`, 120 by default, 0 for as soon as the drain
reaches it. The vblanks stay at 60. VSync still holds the flips to the display's rate, so on a 60 Hz display it
shows nothing without VSync off. Not under frame_cap or frame generation, whose pace is set before it.

## Measured

On an i5-12400F with a Radeon RX 6700 XT, VSync and frame generation off, no mods, the first fight's replay
(build/study/fight_cap.py) once without the patch (A) and once with it at 120 (B):

| Part | A, flips/s | B, flips/s |
|---|---|---|
| boot, logos, title (5-30 s) | 60 | 120 |
| the load and the cinematic (35-60 s) | about 60 | 90-120 |
| the fight (70-95 s) | 38-53 | 39-50 |

- The game's speed, by when the files that streaming opens as Kratos runs came: through the same stretch (HECA100.TS,
  2nd to 18th open) A took 15.2 s and B 16.1 s; from R_HERO00.AS's 3rd open to R_MEGAERA03.TS's 2nd, 7.88 s in
  both. Nothing ran fast.
- The opening movie, played whole without input, once each way: the video clock (the double at 0x9DD138) went
  1.000 s a second in both.
- B started the fight about 6 s later: its loads took 3-6 s longer, the loading screen drawn twice as often beside
  them, and the replay waited at a menu mark it met in another number.
- No error, failure or warning in B that A did not have.
- The fight here is held by the CPU below 60 already: unlocked, it is not faster. Above 60 only the lighter scenes
  go, as far as the CPU takes them.

## Not done yet

- A launcher row (Frame rate: 60, 120, 144, Unlocked), off in multiplayer, and frame generation set apart.
- Scenes beyond the opening: physics, cloth, quick-time windows, the AI and the other readers of the global at more
  than 60 fps.
- The loads: holding the pace to 60 while the title loads.
