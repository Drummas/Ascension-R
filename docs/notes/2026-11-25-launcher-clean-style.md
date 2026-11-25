# The launcher's Clean window style (2026-11-25)

The launcher looked pixelated, most of all at 125%, a common Windows scale on laptops and 1440p monitors: Silkscreen's
dots are whole device pixels only at 100%, 150% and 200% (note 2026-11-12), so at 125% a dot is one pixel or two and the
headings come out uneven and soft; the 16x16 dot icons and the aliased frames and bevels step the same way, and the
scanlines add to it. The body text (Bahnschrift) was never the problem.

**Window style** (`[launcher] style`, `GOWA_LAUNCHER_STYLE`, Display tab): **Clean** by default, **Retro** the look of
2026-11-12.

| | Clean | Retro |
|---|---|---|
| headings, buttons, captions, the name | Bahnschrift, bold and semi-bold | Silkscreen; the name a pixel bitmap |
| icons | Windows' icon font (Segoe Fluent Icons, Segoe MDL2 Assets before Windows 11): `icon_glyph` maps each 16x16 dot icon to its glyph | the dot icons |
| frames, bevels, switches | rounded, antialiased; a bevel is a rounded block with a one-pixel lit edge; a switch a pill with a round knob | square, snapped to device pixels |
| Retro effects (glow, scanlines) | off | as set |
| the header's scene | pixel art at whole device pixels | the same |

The palette is the same in both. The style is read from the row as shown (`clean`), so a choice changes the window at
once: `ui_draw` makes the text formats again (`fonts_make`) when the style they were made for is not the one shown.
Silkscreen is loaded in both, for that.

Also, in both styles:

- **Field of view** (Graphics) is a list: its seven buttons left its text a column too narrow to read.
- The Play tab's quick rows show a list where the buttons would not fit their names: **Frame rate cap**'s six read
  "20 f...", "30 f...", "Unl..." there since 120, 144 and Unlocked were added.
- `GOWA_LAUNCHER_SHOT` also draws the Display tab at its end (Window style and Retro effects).

Checked with `GOWA_LAUNCHER_SHOT` at 96 and 120 DPI, both styles, every tab; the change of style while the window is
open by a shot run that switched it after the first shot (fonts, glow and scanlines followed).
