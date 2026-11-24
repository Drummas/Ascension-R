# Issue #34: the red cell door, a texture unit turned off but still bound (2026-11-24)

One cell door in the statue base (Foot of Apollo, the STATBAS/STAT225 streams) was drawn flat red, bars and brackets,
on every GPU, every time; the reporter's other doors were right. It reproduced here (RX 6700 XT) on the reporter's
saves, Chapter 30, at their settings (render scale 2, bilinear, SMAA, anisotropy 16, shadows off). F9 (every texture
read again) changed nothing.

## How it was found

- A RenderDoc 1.47 capture of the frame (`RENDERDOC_DLL`, F12) and its Python API run headless through
  `qrenderdoc.exe --python` (scripts in `build/issues/34/work`, not kept in the repo): pixel history at the door on
  every colour target. The first red write is the door's own draw into the scene colour target 0x00E10000; every later
  pass only carries it on.
- That draw's pixel debugged: every colour texture it samples is grey (0.23-0.63). Its unit 4 returned (11.9, 0, 0,
  1): the X32_FLOAT target at 0x03244000 (a linear depth, remap 0x09E4: R, then G and B zero, A one). The program
  multiplies a lighting term (8 x N.L) by unit 4 per channel, so red came out at 34 and green and blue at 0.03.
- The draws before it bind that target at unit 4. The door's draw turns unit 4 off (SET_TEXTURE_CONTROL0 bit 31
  clear). `d3d12_bind_texture` never read that bit, so the unit kept the earlier draw's texture.

## The fix

A unit the title turns off is left unset, a null view that samples 0, as on the RSX. `RSX_TEX_ENABLE=0` binds units
whatever the bit says, as before. The door is right again on the reporter's saves; the bench to Megaera's arena looks
as it did. Units turned off and still sampled could explain other wrong colours that depend on what an earlier draw
left, so issue #9's reports are worth another look with this build.

## Play bed

`build/issues/34/play/play-34.bat` (local only): the dev build on the reporter's saves and settings, the port's own frame
capture on F12, RenderDoc with `rdoc`, A/B words for the texture switches, `reset` for the saves.
