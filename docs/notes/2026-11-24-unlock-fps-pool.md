# Unlock FPS and the VRAM pool: the hangs as levels load (2026-11-24)

Issue #39's tester (Ryzen 5 5600X, RTX 5060) had the game stop as levels loaded with DLSS test builds 1 and 2. Test
build 2's counters and their own A/B settled what does it, not yet how.

## What the reports say

- Every hang came with the Frame rate cap Unlocked, with DLSS and with FSR: 4 of their 6 unlocked sessions and 1 of
  2 in their last A/B (FSR unlocked stopped, DLSS unlocked went through). With the cap Off, none, at 720p to 4K, and
  far less graphical corruption.
- Two places: as HECA100 loads (the first blade, at the start of a new game) the pool was full, 191.4-191.9 MB live
  with 0.3-0.8 MB of holes; as HECA200IGC loads (the Megaera cinematic after the parasites), 159.4-159.9 MB live with
  32-33 MB of holes not packed yet, 1,098 blocks both times. Then an allocation of 0x15560 or 0x2AAB0 bytes failed and
  the game wrote the texture's fields to address 0 and stopped (docs/notes/2026-11-24-dlss-test1.md).
- The manager made its pass in 574-599 of the last 600 frames at each shortage: it did not skip work.
- Their sessions ran ~170-177 frames a second on average (menus and loads included).

## The pool on this PC

The per-load line (`[vram] load of ...`: the pool before a load, at the least room an allocation left, after it) and
`GOWA_VRAM_STATS=<seconds>` (frames, the manager's passes and bytes moved, allocations, trims, grows, the pool) were
added for this. The bench's route (Continue, the opening cinematic, the Megaera fight), FSR at 720p, VSync off, a line
a second, the cap Off against Unlocked:

| | Off | Unlocked |
|---|---|---|
| Frames a second in the level | 52-53 | 52 (CPU bound either way) |
| Loading the level (HECABAS and 14 more) | 17.4 s, 1,004 frames | 13.8-14.4 s, 3,953-4,436 frames |
| Least room in the level | 0.0-0.7 MB | 0.0-1.0 MB |
| Most holes | 61-66 MB | 57-63 MB |
| Allocations, trims a second | 4.9-5.2 MB, 0.32-0.36 | 4.0-4.4 MB, 0.25-0.29 |
| Shortages | 0 | 0 |

The pool runs at its edge by design: as the level streams in, its room falls to about nothing with 55-65 MB of holes,
then comes back by ~50 MB at once, every 5-6 s, with the cap off too. A shortage is an allocation larger than what is
left at such a low point.

## Two paces that count frames, ruled out here

- The loaders (func_0003D70C, func_003F863C) work each frame until a fifth of a 60 Hz period has gone (the time count
  func_002CA76C over five, back at 0x0003DC04 and 0x003F87A8): at 170 frames a second three times the loading a second
  of 60. A budget three and six times as large at 53 frames a second (a test hook, since taken out) changed nothing:
  4.8-5.4 MB a second allocated, the same cycle, no shortage. The loaders are not what limits how fast data comes in.
- The streaming pass trims one texture a pass, the oldest whose stamp is more than [0x83CD44] = 240 frames behind the
  frame counter at 0x9B9988 (+1 a frame): 4 s at 60, 1.4 s at 170, 0.24 s in a menu at 1000. Forced to 73 frames
  (`GOWA_TEXTURE_AGE`): trims stayed at 0.2-0.3 a second and the pool the same.

The bench's route never reaches HECA100 or HECA200IGC, and this PC cannot run the level above ~52 frames a second, so
neither the hangs nor what at a high frame rate leads to them could be made here.

## What test build 3 does

- **While a level loads, Unlock FPS is held to 60 frames a second.** vram_guard.cpp opens a window on each load (the
  level's archives opening, through the file system's open hook, until 4 s after the last) and sets
  `g_gowa_level_loading`; main.cpp's frame clock then waits one vblank period between flips. The loads run as with the
  cap off, which has not stopped; between loads the frame rate is unlocked.
- **A texture counts as old after 4 s at any frame rate.** With Unlock FPS the limit at 0x83CD44 is set each frame to
  the frames of 4 s (the frame's step at 0x9424A4 times the rate at 0x83B45C, smoothed over ~16 frames), never under
  240, and back to 240 when the patch goes off (online). The title only reads it. For the corruption the tester saw
  unlocked, not shown to change the pool here.
- **The per-load line**, in every log: the tester's reports will say how close each load came, unlocked and off, at
  the two places this PC cannot reach.
