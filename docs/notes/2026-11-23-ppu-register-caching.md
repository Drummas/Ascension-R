# Guest registers in C locals, measured: no gain here (2026-11-23)

The other GoW:A port (bc160201983/GoW-Ascension-Recomp) lifts its PPU code with the guest registers in C locals
(its ppu_lifter.py `_cache_regs`, `--cache-regs`), and its 0.2.0 credits "faster recompiled game code", busy fights
17-19% faster on its 16-core test PC, to write-back caching with inline stores and VMX helpers. This port's lifter
does neither. The pass was brought over behind a switch and measured against this port's own lift.

## The pass

`ps3recomp/tools/ppu_cache_regs.py`, `ppu_lifter.py --cache-regs wt|wb` (`gowa.py lift --cache-regs`), off by
default; tests in `ps3recomp/tools/test_ppu_cache_regs.py`.

- Each GPR, FPR and CTR a function uses gets a C local, loaded where it is first read after the entry or after a
  statement that hands `ctx` out. `wt` stores every change to the context as well; `wb` stores what may have
  changed only before such a statement, a return or the end of the body.
- CR and XER are left to `--lazy-flags`, whose macros read and write `ctx->cr` and `ctx->xer` where a text pass
  cannot see them; VRs, LR and the rest stay in the context.
- Safe on this lift: over the 22,320 functions no statement spans lines (patched instructions, switches and VMX
  loops are one line each), there is no computed goto, the header's macros touch only `cr` and `xer`, and the
  exception handlers only read a context, for their reports.

## Measured

i5-12400F, RX 6700 XT, `gowa.py bench --runs 2 --early-stop 0` on build/bench-hdd0 (frame generation and VSync off,
multiplayer off), four executables of one source, in ABBA order:

| Run | Flips a second (median) | `ppu main` % | shader builds % |
|---|---|---|---|
| plain 1 / 2 | 37.06 / 44.42 | 74.6 / 98.2 | 424 / 0 |
| `PORT_PPU_RESTRICT` 1 / 2 | 37.20 / 43.84 | 75.9 / 98.1 | 426 / 0 |
| `--cache-regs wt` 1 / 2 | 37.53 / 43.55 | 75.6 / 98.0 | 428 / 0 |
| `--cache-regs wb` 1 / 2 | 37.29 / 43.38 | 74.3 / 98.3 | 422 / 0 |

- The first round ran with every shader still to build (each new executable, its own cache), the second without:
  hence 37 against 44, for all four alike.
- Against plain, averaged over the two rounds: restrict -0.5%, wt -0.5%, wb -1.0%; the same executable's runs
  differ by ~1.3%. No gain, in either round.
- The executable grows: restrict +2%, wt +5%, wb +8.7%.
- The main thread is busy all the time in every build (98% with the cache warm), but most of that time it waits:
  the 2026-11-18 samples of this fight had 30% outside the executable, 20% in one spin-wait predicate and 11.5% in
  the poll wait. The frame is set by the SPU job chain (docs/notes/2026-11-18-parasite-fight-probes.md), so the
  PPU code running faster shortens a wait and not the frame.
- `PORT_PPU_RESTRICT` was worth "another run after lazy CR" (docs/notes/2026-11-06-main-thread-review.md): this is
  that run, and it stays off.

The switch stays, off, for a scene or a PC where the main thread's own work sets the frame. Not tried: a 4-core CPU,
the other port's inline stores and inline VMX helpers, and a PGO build of the cached lift (that port turns clang's
loop peeling off for it: `-mllvm -unroll-allow-peeling=false`).
