# Where Kratos's joints are put together: the hero's animation job (2026-11-21)

The proportions of [2026-11-19](2026-11-19-proportions.md) change a mesh's palette on the skinning jobs, so only that
mesh's skin follows the new lengths. The blades in his hands, the chains, the blades on his back and the effects stay
where Kratos's joints would be: with a mod's shorter arms the blades would float 0.16 to 0.26 units off the hands.
The lengths have to change where the joints are put together, before anything reads them.

## Finding it

- **Who writes the palette array.** A temporary probe set hardware write watches (the debug registers, on every
  thread) on the joint array a hero skinning job reads (slot 18), and kept each writer's stack (`RtlVirtualUnwind`,
  named through the linker map). The arrays move a little every frame (a per-frame allocator), so the watches caught
  every writer of that memory; one was SPU job module `0243f9351a06` (entry 0xBB40), writing 4x4 matrices.
- **What that job reads and writes.** `SPU_JOB_CAPTURE` of that module alone, during play (a temporary entry filter),
  and in the same run the hero's palette arrays dumped from the skinning jobs. Each dumped palette, times the body
  skeleton's binds, is a world matrix; those were found among the job's PUTs, in arrays of 16384 + 320 bytes: 261
  matrices.
- **The skeleton.** The job GETs a 2096-byte table that is R_HERO00.WAD's template skeleton `heroA` (an unnamed type
  0x2D entry, 261 joints, the records from +0x24: 8 bytes a joint, the parent in the fourth u16). Its joints are the
  bodies' 155 (the same names, parents and bind positions) and 106 of its own: `leftChain1`/`rightChain1` on the
  wrists, `rWeapIH`, `lWeapIH`, `rightBladeBack`, `leftBladeBack`, holsters, the chains' `JOchainJointLeft1-10`, IK end
  effectors and solvers, `JOIKGroundPlane1`.

## What the job does with it

- For the hero it GETs the table, then the 261 **local** matrices (row vectors, the translation in row 3: the bones'
  lengths, the forearm 0.355, the shin 0.662) from a buffer that stays from frame to frame, then **last frame's world
  matrices**.
- It builds world = local x world(parent) in place in its local store (all 260 joints with a parent check out), PUTs
  the new world array to a per-frame buffer, and PUTs last frame's array again beside it, unchanged (for the
  velocity). Next frame it GETs its own output back only as last frame's.
- The skinning's palettes are made from that world array later (Kratos's matched it to 1e-3), and the weapons and
  chains hang on its joints.
- Other jobs GET the same table too (one before its own code is loaded).

## The hook

- `runtime/spu/spu_dma.h` (the fork): `g_spu_get_hook`, called after each GET that went through, when a program sets
  it. Unset, the transfer path costs one load more.
- `port/skel_prop.c`: a mod's `"where": "animation"` file names the table by its size and an FNV-1a hash of its
  records, and gives each joint a ratio. When the animation job (its first 32 bytes of code at LS 0x4030) GETs that
  table, its next GETs of 16384 and 320 bytes are the locals, and their translations are multiplied by the ratios in
  the local store. The game's buffer keeps the animation's own, so nothing builds up from frame to frame, and last
  frame's array is left as it came. The first piece is checked first: at least 70% of the joints with a bone of 0.05
  or more must have the template's length within 2%.
- `scripts/proportions.py`: `"where": "animation"` writes the file from R_HERO00.WAD (a skeleton without a name is
  found by its first joint's name); `--binds` writes into a copy of R_HERO00.AS the body skeletons' local tables and
  inverse binds of the new lengths, for a mesh modelled in that rest pose.

## Tests

- `tests/test_proportions.py`: the animation file of a made-up unnamed template (its table hash, ratios by name, bind
  lengths) and `--binds` (the local table and the inverse binds of the new rest pose, the template left alone).
- The game, the parasites' fight replay with Kratos's own meshes: elbows and wrists at 0.6, the arms short and the
  blades in his hands, the chain coming out of the hand when he swings. A mod's whole set of ratios (92 joints): the
  shoulders narrow, the feet on the ground, the blades on the back on the new back. The bench route: no table left
  without its locals (`[props] heroA.bin: 261 joints take the new lengths ...`).
- Pad replays drift apart from run to run with or without the hook, so they say nothing about the reach.
