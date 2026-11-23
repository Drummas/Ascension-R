# The bloom back: Disable MLAA on the SPU side (2026-11-23)

Disable MLAA, on by default, made the title take its frame order without MLAA. In that order the bloom and the motion
blur are drawn right after the flip and the next frame's fog pass writes over them (docs/notes/2026-11-03-fsr3.md,
section 3), so a player with the default settings never saw the bloom. In the order with MLAA the same passes run before
the final composite. The other GoW:A port (bc160201983/GoW-Ascension-Recomp) keeps its glow with RPCS3's "Disable SPU
MLAA" patch, which stops the SPU's anti-aliasing and leaves the title's order alone; that was the lead.

## The SPU program

RPCS3's "Disable SPU MLAA - God of War: Ascension (01)" (Whatcookie) is for the SPU program named
`z:/export/jenkins/workspace/int6` and loads its SPU_MLAA_05 pair: `il r2,0` at LS 0x4440 and `il r10,1` at LS 0x56C4
(patch.yml's comment says `il r10 0`; the word 0x4080008A is `il r10,1`).

This ELF embeds four SPU programs at 0x3000. Three carry that name; the one whose words at those two addresses write r2
and r10 is the MLAA task, sha256 `8e4f2136...a94b4d8` (analysis/spu/spu_0001_at_006C1B00.elf, 39,508 bytes):

| LS | Was | Is | Then |
|---|---|---|---|
| 0x4440 | `clgt r2,r6,r9` | `il r2,0` | `brz r2` at 0x445C always skips the block, to 0x4548 |
| 0x56C4 | `andc r10,r27,r26` | `il r10,1` | `brnz r10` at 0x56C8 always takes the way out, to 0x6148 |

The tasks still run and signal; they only do no work. Their output, a copy of the frame in main memory, was never what
this port shows (its frame stays on the GPU), so the picture keeps the title's MLAA order and loses nothing.

## The patches

- `disable_mlaa` (same id and guard, on by default, so a saved `disable_mlaa = on` carries over): these two SPU edits now.
- `mlaa_path_off` (new, no launcher row): the old edits, the MLAA word 0x83D004 at 0 and the two `bl 0x397408` nops.
  main.cpp switches it on with AMD FSR (`graphics.scaling = fsr3`) or frame generation (`on`, `anr`): with MLAA the
  depth at the final composite is the next frame's. FSR stays off without it, and Disable Motion Blur is left off for
  FSR's motion only with it. So with FSR or frame generation there is still no bloom.
- The Play tab's ready check no longer asks for Disable MLAA with FSR.

## Edits of an embedded SPU program

The title patches could edit job modules only (lift_jobmods.py). An `spu` edit may now name an embedded program by its
sha256 (`"image"`, the whole digest or 12+ hex digits) instead of a `"module"`:

- gowa.py checks the word at the LS address in the ELF's own copy of that program, and writes the image edits to
  analysis/GOWA.spu_image_insn_patches.json;
- build_spu_workloads.py `--insn-patches` (ps3recomp): spu_program_pipeline.py hands each program its own edits, and
  spu_lifter.py `--insn-patches` lifts both forms behind the guard; an edit of a program that was not found stops the
  run unless it is optional;
- the dev build passes the file through CMake (`PORT_SPU_INSN_PATCHES`, `PS3RECOMP_SPU_INSN_PATCHES`), the Kit's module
  build straight to build_spu_workloads.py. The lift log says `2 insn patch(es), lifted both ways`.

## The Kit's DLL

The lifted code reads each patch's guard; in the Kit's ascension_game.dll that is the DLL's own copy, set from
GAME_MODULE_DATA (port/game_module.h). `g_gowa_patch_unlock_fps` (Unlock FPS, earlier today) was not in it, so the DLL
would not have linked on a player's PC; a source build links everything into one exe and did not show it. It is there now
with `g_gowa_patch_mlaa_path_off` (GAME_MODULE_ABI 9), and tests/test_game_module_hooks.py checks every guard of
scripts/title_patches.json against that list. The copy is taken once, at the DLL's start: when the game goes online and
Unlock FPS is taken back, the DLL keeps its patched frame sync, which with the constants back and the frame clock at the
vblank period steps by the real frame time (a floor of 10 ms), as the title's own does at 60.

## Measured

i5-12400F, RX 6700 XT, bilinear scaling, VSync off, no mods; the first fight's replay, one run each:

| Run | Order | Flips a second in the fight |
|---|---|---|
| M1 | without MLAA (`mlaa_path_off`), the old default | 40-54 |
| M2 | with MLAA, SPU work off (the new default) | 39-52 |
| M3 | with MLAA, SPU work on | 37-47 |

- No hang in seven runs of the MLAA order (three fight replays, two from the #34 save, two to the title).
- The replays part ways from run to run, so no two screenshots show the same frame; that the bloom reaches the picture
  in the MLAA order rests on the 2026-11-03 frame captures.
- In one of three M2 replays, at 70 s, a few surfaces of the rooftop were striped, many-coloured garbage; not in the
  other two at 66-78 s, nor in M1, M3 or the save runs. The #34 reporter (MLAA order) and the #9 reporter (the order
  without it) both saw such garbage, so it is not this order's, but it is the first time the #9 kind has been seen on
  this PC's RX 6700 XT.
- The look varies from run to run in the same settings: some runs darker, with hard black patches, and banding in the
  title's background. Seen in both orders; not looked into.
