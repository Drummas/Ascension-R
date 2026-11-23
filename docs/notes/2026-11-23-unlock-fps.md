# Unlock FPS: the patch, the pace and the launcher row, measured (2026-11-23)

The title steps its world by the real time of each frame, and above 60 frames a second it ran fast. This adds the
title patch `unlock_fps` (scripts/title_patches.json) and the frame clock's pace for it, switched on by the launcher's
Frame rate cap at 120, 144 or Unlocked (experimental). Step 1 made the patch and measured it behind switches. Step 2,
the same day, found that step 1's design slowed the loads, replaced it, and added the launcher row and what frame
generation and multiplayer do with it. The map was the 2026-11-17 study (docs/notes/2026-11-17-flip-period.md) and
RPCS3's "Unlock FPS" v2.0 for 1.04, each site read back from this ELF.

## The title's timing

- func_002D01E8 sets the rate once at init: 59.94 from the table at 0x3A52B4, stored to the global 0x83B45C, and
  int(rate + 0.5) to 0x9424A0, which only the sync reads.
- func_002D0258, each frame: the timebase ticks since the last frame (0x9424C8) over the time count's ticks a period,
  times 100, clamped to 100-400 (the pool constants at 0x2D0248/0x2D024C) and divided by 100, so 1-4 periods, and no
  less than rate / int rate (0.999 periods). The frame's step in seconds (0x9424A4) is that over the rate. Mode
  0x9424A8: 0 that variable step, 1-3 the same averaged over 8, 30 or 15 frames, 4 a fixed two periods (the 2.0 at
  0x2D0254); 0x9424D8 forces one period. A frame under 16.7 ms still moved the world 16.7 ms: above 60 fps the title
  ran fast.
- The time count func_002CA76C (the timebase's ticks in a period) has four callers: the sync, two loaders (func_0003D70C
  and func_003F863C, each working through its queue until a fifth of a period has gone in the frame) and func_003B6878
  (a time as a percentage of a period).
- The global is read by 12 functions. The time count, the sync (twice), the video player (func_003F5748, whose clock
  takes 1/rate each frame) and the video clock's reset take it as a time base. The others scale gameplay by it, each
  times a step in seconds (0x9424AC, the step with the time scales, or an object's own at +0x584): speed by step by
  rate; smoothing factors of step by rate by k (func_0026C590); func_001E0B78's x / (1 - x * periods), the same for
  two half steps as for one; and the physics update func_00191BA8, which runs floor(substeps * step * rate + 0.99) substeps of step / n
  each: at 120 a body of one substep a period still gets one a frame (0.5 + 0.99), and none gets zero above 1 ms. They
  keep 59.94.

## Step 1's patch, replaced

Step 1 made the period 1 ms: the rate table 1000, the rate's store a nop with the global kept at 59.94, and the time
count, the sync and the video player reading 1000.0 from a TOC word. It ran at the right speed, but the time count's
1 ms periods reached its other callers too: the loaders' budget went from 3.3 ms of a frame to 0.2 ms, and the first
level's load took 3-6 s longer at 120. Holding the pace to 60 while a level's files opened made it longer still:
fewer frames, so less budget.

## The patch

Six instruction edits and two data edits. The rate, its global, the time count and the loaders stay as they were:

| Where | Was | Is | Why |
|---|---|---|---|
| 0x2D0248 | 100 | 1000 | the sync counts the step in thousandths of a period |
| 0x2D024C | 400 | 4000 | the ceiling stays 4 periods, 66.7 ms |
| 0x2D0398, 0x2D039C | fsubs f4,f29,f2; fsel f2,f4,f29,f2 | the same with f1 | the floor is f1, the rate (59.94): 0.06 periods, 1 ms |
| 0x2D03B0 | fsel f31,f3,f2,f31 | fmr f31,f2 | a measured step loses the floor of rate / int rate |
| 0x3F678C, 0x3F6798, 0x3F67A0 | addis r4,0,0x84; lfs f31,0xb45c(r4); fdiv f31,f1,f31 | addis r4,0,0x94; lfs f31,0x24a4(r4); nop | the video clock moves by the frame's step instead of 1/rate |

- The pool constants 0x2D0240-0x2D0254 are func_002D0258's alone (Ghidra's references); the scale is read there for
  the multiply, the floor and the divide.
- In the video player r4 is set again before any other read of it, on both paths after the load. The audio's time
  still sets the clock when one comes.
- A frame's step is now its real length from 1 ms to 66.7 ms. A step not measured (flag bits of 0x83B460) and the
  forced one keep their period.

`[patches] Unlock FPS (experimental): on (6 PPU and 0 SPU instruction edits, 8 data bytes)` in the log.

## The pace and the launcher row

- The Frame rate cap row (Display tab, `display.frame_cap`) has 120, 144 and Unlocked (experimental) beside Off, 20
  and 30. Any of the three switches the patch on: main.cpp sets GOWA_PATCH_UNLOCK_FPS before the patches are applied,
  to 0 for the other choices, so a `[patches] unlock_fps` line in the file is passed over. `--set
  patches.unlock_fps=on` and GOWA_PATCH_UNLOCK_FPS=1 still switch it on by themselves, at 120. The Patches tab does not
  list it.
- The frame clock holds a flip no sooner than 1/cap s after the last; with Unlocked, not at all
  (`display.fps_limit` or GOWA_FPS_LIMIT in place of the cap). VSync still holds the flips to the monitor's refresh.
- Frame generation is off with it (main.cpp overrides `graphics.frame_generation` before the renderer starts): it
  would hold the game at half the monitor's refresh, 60 at most. The launcher's footer shows the cap in its place.
- When the game goes online for multiplayer (func_0040A560's hook, where the cheats go off), gowa_title_patch_off
  (patches.cpp) writes the two constants back and clears the guard, so the title runs its own instructions again, and
  the frame clock goes back to one vblank period, until the next start. A function halfway through when that happens
  may run once with the two mixed.

## Measured

i5-12400F, RX 6700 XT, VSync off, no mods; the first fight's replay (build/study/fight_cap.py), each run once. The step
check read 0x9424A4, 0x9424C8 and 0x9424D0 about every millisecond while the game ran (each new 0x9424D0 is a frame)
and set each frame's step against its ticks over the timebase's 79.8 MHz.

| Run | Pace | Hero's WAD to Megaera's | to her TS's 2nd open | each frame's step / its length |
|---|---|---|---|---|
| A, G | 60, no patch | 7.9, 7.6 s | 19.0, 17.1 s | median 1.000-1.006, p95 up to 1.16 |
| B | 120, step 1's patch | 10.7 s | 22.5 s | |
| D | 120, step 1's patch, 60 while a level's files open | 15.4 s | 30.1 s | |
| E, F | 120, this patch | 6.5, 4.8 s | 16.3, 12.8 s | p5, median and p95 1.000 |

- At 120 every frame moved the world by its own length. Without the patch, frames that came sooner than a period
  still moved it a whole one: at 60 the menus and the cinematic ran up to 1.8% fast.
- The loads are shorter at 120 than at 60: the loaders take a fifth of a period each frame, and there are twice the
  frames.
- Flips a second at 120: 120 at the title and menus, 90-120 through the load and the cinematic, 37-53 in the fight,
  as without the patch (36-53): the CPU holds it.
- The opening movie at 120 flips a second: its clock went 1.000 s a second, within 0.4% in each 2 s.
- F ran with this PC's own settings, multiplayer on Auto and frame generation on: frame generation went off, and the
  patch stayed on through the single-player run.
- Multiplayer (scripts/mp_local.py, the title to Quick Play): 120 flips a second until `SamStateStart::connect`, then
  `[patches] Unlock FPS (experimental): off` and 60 from then on.
- Step 1's streaming stretch (HECA100.TS's 2nd to 18th open) is no measure of speed: 15.2 and 16.7 s in two runs
  without the patch, 16.1-16.5 s with it.

## VSync on a 120 Hz display: three buffers

First play on a 120 Hz display, Unlocked with VSync on: the opening movie at 120, Village of Kirra at 60. The swap chain
had two buffers: under VSync a frame that took longer than a refresh (8.3 ms) held the next until the refresh after,
so a game that ran 70-110 on its own was shown at 60. With Unlock FPS the swap chain has three
(`D3D12_SWAP_BUFFERS=3`, which main.cpp sets with the patch; rsx_d3d12_backend.c keeps two otherwise, frame generation
and the 60 of the vblanks included, where a third buffer would only add a frame of delay).

- The player's own session played again (its pad, its saves as they were at its start), Unlocked, VSync on, FSR 3 at
  1.5x, one run each: Village of Kirra, 70-100 s, two buffers 84, 59, 57, 51, 56, 58, 60 flips a second; three 113, 83,
  76, 67, 66, 68, 72.
- The descriptor slots of the presentation passes were laid out for two display targets: `PP_SLOT_UP` for the
  upscaler and SMAA's weights overlapped with a third, and the AMD driver crashed in `fg_targets` at the first FSR
  frame. Every per-target run is FRAME_COUNT (3) long now, checked by a static assert.
- Two buffers again checked with SMAA and bilinear, and with frame generation on (60 flips a second, a 120 Hz display):
  no crash, no D3D12 error, the picture whole.

## Not done

- A 144 Hz monitor.
- Frame generation from a game above 60 (72 for a 144 Hz monitor).
- The game beyond Village of Kirra at more than 60.
