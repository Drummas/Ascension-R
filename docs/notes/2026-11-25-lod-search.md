# Level of detail further away: where it was looked for (graphics plan item 6, 2026-11-25)

Not done. What a first search found, for the next one.

## What is not there

- No string in `GOWA.elf` names a level of detail, a LOD distance or a detail setting.
- The model format study (note 2026-11-19) found sub-blocks in a part (a sphere and a box each), not LOD levels or
  distances; nothing there says the game keeps several meshes of one model by distance.
- The `renModelServer` vtable's functions take no square root and compare no floats: they manage, they do not choose by
  distance.

## Leads

RTTI (name -> typeinfo -> vtable -> OPD -> code, `build/issues/gfx6/rtti.py`):

| class | vtable | slots (first) |
|---|---|---|
| `renModelServer` | `0x6A6108` | `func_005F6098`, `func_005F68E4`, `func_002FAD64`, `func_0039461C`, `func_002FB0A0` ... `func_002FBAE4` |
| `renModelServerContext` | `0x6A6080` | `func_005F6490`, `func_005F64E0`, `func_00539C1C`, `func_00393484` ... |
| `renModel` | `0x6A66E8` | `func_003ADF04`, `func_003AE04C`, `func_005E6E2C` |
| `renModelModifier` | `0x69115C` | `func_0053BD10`, `func_0053BD20`, `func_004576C0`, `func_0053BD60` |
| `SCR_IgnoreCulling` (a script command) | `0x696370` | `func_005600A8` ... |

Also `stdArray<renModelGroup const*>` (a model's groups), `svrTree` / `svrSortedListContainer<goClient>` (the scene's
spatial tree) and `anmVisible`.

The render core sits around the cameras (`func_003AFDC8`, `func_003B0380`) and the render settings (`0x9B99B8`, getter
`func_003B6180`). Its functions from `0x380000` to `0x3C0000` that take a square root and compare floats, the shape of a
distance test: `func_00382338`, `func_00384F68` (16 float compares), `func_003A6310` (8 square roots, 22 compares),
`func_003A8990`, `func_003A9EB0`, `func_003B4808`, `func_003B4D00`, `func_003B5290`, `func_003BAA88`, `func_003BB5F0`,
`func_003BC1F0`, `func_003BC4A8`, `func_003BD660`.

## How to go on

- A probe on those candidates' entries (call counts a frame, which object): a LOD choice runs once per drawn model a
  frame. Then the one that reads a model or group field against a distance or the camera's half-width (`+0x3C0`).
- Or from the other side: the culling the title does with the camera's numbers (the ultrawide note: its frustum comes
  from the same two values), as a LOD test is often next to it.
- Whether the game swaps meshes by distance at all: a model watched from near to far, its draw's vertex count in
  `RSX_CAP` frames.
