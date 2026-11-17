# What the parasite fight waits on: slow-down probes (2026-11-18)

The first level's fight with Megaera's parasites runs 40-60 flips a second on an i5-12400F (six cores, twelve
threads) with an RX 6700 XT, EU disc, the exact-60 flip pacing (`ab62647`): 54-55 on the average, dips to 42-44.

## The setup

- **The fight, replayed.** A session of the fight from the launcher, its pad recording copied out of `build\logs`, and
  `PAD_REPLAY=<copy>` with `--no-launcher --set display.mode=windowed --set paths.hdd0=<a copy of the saves>
  --set cheats.damage_taken=0`. The saves are put back from a copy taken before the recorded session, before every run,
  so each run starts from the same checkpoint. 165 s a run, `GOWA_THREADS=2`, `SPURS_WID_PROF=2`, `D3D12_VSYNC=0`.
- **Measured:** the fight part of the replay, 60-110 s after the start, 26 windows of 2 s.
- **`build\logs` keeps the newest five sessions,** logs and pad recordings alike. A first series of these runs replayed
  a recording that the runs themselves pushed out of the folder, and measured the menu. Copy a recording, and each
  run's log, out of the folder before starting more sessions.

## The probes

Each run slows one part by 25%: `GOWA_MAIN_SLOW` the main thread's own work, `RSX_SLOW` the frame clock thread's,
`SPURS_WID_SLOW` the named workloads' policy-module runs. A part the frame waits on makes the fight slower; a part with
slack does not.

| Run | Flips/s, fight | Against the baselines |
|---|---|---|
| baseline 1 | 54.55 | |
| main thread +25% | 49.98 | **-8.6%** |
| frame clock thread +25% | 53.86 | -1.5% |
| EDGE (w14, w15, w16) +25% | 53.78 | -1.7% |
| RenderJobs (w12) +25% | 53.78 | -1.7% |
| RenJobSet (w8-10) and MeshProc (w13) +25% | 53.71 | -1.8% |
| General6 (w2) +25% | 51.52 | **-5.8%** |
| baseline 2 | 54.86 | |

The two baselines are 0.6% apart.

## What it says

- **The main thread's own work is all on the frame.** In the fight it is 300-400 ms a second (about 7 ms a flip, 1.4-1.8
  M indirect calls a second). The probe added ~1.7 ms a flip and the flip took 1.73 ms longer. So each millisecond taken
  off it is about +5% here (a flip is 18.3 ms), and a fifth off it would bring the fight's average close to 60.
- **General6 is next,** about half of the time it was given showed on the frame.
- **EDGE, RenderJobs, RenJobSet, MeshProc and the frame clock have slack.** The frame clock thread was given ~2 ms a
  flip and lost 0.3. The EDGE levers in [S and J](2026-11-16-s-j-review.md) would not show in this fight.
- **What the fight is not:** kept fills (as in [Kirra](2026-11-16-kept-fills.md)), the index buffer, resident restarts,
  the GPU (56%), or interpreted SPU code. EDGE's memo found a result for 97.4% of 4.9 M jobs.

## Next

1. A profile-guided build of the lifted PPU code (`PORT_PPU_PGO`, with `PORT_SPU_PGO` for General6), trained on this
   replay and measured on it against the plain build.
2. A sample of the main thread in the fight, for the functions its own work is spent in.
