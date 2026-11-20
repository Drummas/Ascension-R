# The Grotto at 30 flips a second: General6's noise runs in full there (2026-11-20)

Issue #27: on 0.2.0 the swim in Chapter 15, The Grotto, runs at 24-28 fps by the reporter's recording, against 27-29 at
the same spot on 0.1.0-alpha.15. The reporter sent their saves. Renamed to the European disc's id, they load here, and
Continue Game on their Profile 1 puts Kratos in the room after the two ice brutes (CYN850), about two minutes before the
swim. Their own session ran that room at about 50 flips a second.

## Where the time goes

On an i5-12400F with a Radeon RX 6700 XT, at the reporter's settings (render scale 2, SMAA, MLAA on, shadows off),
Kratos standing still in that room: 30.3 flips a second.

- Threads: `ppu main` 98% (its waits for SPU job chains spin), the SPURS policy modules 221-242% of a core, the frame
  clock 45%, the render thread 7%. The vertex pass lit everything on the GPU there (26,700 segments a second, none on
  the CPU, none short of room); the EDGE memo answered 96.6% of 3.8 M jobs; no SPU code in the interpreter.
- SPU time by workload (`SPURS_WID_PROF`), share of one core:

  | workload | busy | a run | runs a second |
  |---|---|---|---|
  | w2 General6 | 76.7% | 598 µs | 1,282 |
  | w12 RenderJobs | 25.5% | 341 µs | 747 |
  | w3 | 24.1% | 337 µs | 717 |
  | w14-16 EDGE | 22% each | 512-522 µs | ~430 each |
  | w7 audio | 16.7% | 114 µs | 1,458 |
  | w8-10 RenJobSet | 19% together | | |

  General6 is ~43 runs a frame, ~25 ms of worker time a frame. In the first level's fight it was 55%.
- General6's samples (`PS3_SAMPLE_THREAD=spurs pm`, `symbolize --wid 2`, 31,288 samples over 80 s): the noise job
  module `a67e549fa0ab` takes 82%: `0x4F00` 38.9%, `0x4AB0` 24.8%, the pixel loop `0x63B4` 11.5%, `0x4930` 4.7%,
  `0x4E9C` 2.2%. The other module, `1bdd67b54c3b`, ~5%; the native General6 routines (`gowa_g6_*`) ~6%.

## Why it is dear here

In the first levels the noise job's record has its scale at zero: every noise call gets zero arguments, and
`gowa_g6_noise_4930` and `gowa_g6_cell_63b4` cut the work to a test and one pass a cell
(docs/notes/2026-11-05-general6-noise-review.md). In the Grotto the scale is not zero, so neither applies and the
four octaves run for every pixel, as lifted code: `0x4930`'s chain is ~860 SPU instructions a call.

## It is on the frame's path here

General6 25% slower (`SPURS_WID_SLOW=2:25`), one run against the baseline: 27.75 flips a second against 30.33, -8.5%.
At the gate the same probe changed nothing.

## Not done

- A native noise (the chain `0x4930`, `0x4AB0`, `0x4E9C`, `0x4F00`, four lanes as the SPU's): it has to give the SPU's
  results, and a capture of the Grotto's noise jobs to check it against.
- Why General6 stays under one core here when its workload allows six SPUs (`maxContention` 6): if the 16 tiles of a
  band could run side by side, the chain's wait would shrink without touching the noise.
- The swim's own spot: the reporter's logs show the vertex pass out of room there (alpha.15 and 0.2.0 alike); a
  playback from the checkpoint drifted before it.
