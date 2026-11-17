# Skipping the intro, the movies and the cinematics (2026-11-17)

Issue #15's reporter asked for a way past the opening movie on a fresh install. This reads what the game has, then
what the two patches made from it do.

## What the game has

- **Its movies** are MPEG-2 streams (`.M2V`) in the archives, played by the game's own player through cellVdec (the
  calls come from the code around `0x003F4DF0-0x003F5748`, driven by the boot sequence `func_0020848C`); no cellDmux or
  cellPamf. About 25: the opening one before the menu (`INTROCIN.PSARC: OPENINGINT6.M2V`, OpeningInt6 to the code), the
  levels' (`HECA.PSARC: SPGAMEINT00`, `HECAHANDTRANS`, `HECAHEADTRANS`; `CRTN`, `CYN`, `FURY` with `CREDITS`, `LAN`,
  `STAT`, `STINT`), the multiplayer one (`MPGAMEINT`), and the fourteen behind-the-scenes extras (`EXTRASCIN1/2:
  BTS_*`). The cinematics in the engine are drawn as the game plays, not from a file.
- **Its own way past them**, tried here on the US release with new profiles:

| | The opening movie | A level's movie (SPGAMEINT00, at the first level) |
|---|---|---|
| First start (no system save yet) | nothing ends it: Square, Cross, Circle, Triangle, Start, Select; 141 s | Select opens **Pause: Continue, Skip Cinematic, Quit Game** |
| Any later start | a face button ends it | the same |

Start does nothing in a movie. The first version of this note had Start for the pause menu and took its silence on a
first start for a lock; the button is Select, and the pause menu opens on a first start as well. So only the opening
movie is locked, and only until the first system save: a player who starts from an empty folder meets it each time.

## Where the lock is

Two first and later starts on the same profile, the data segment read twice in each, 30 and 40 s into the opening movie
(`ReadProcessMemory`, the way `guestscope.py` finds the guest's memory): of the bytes that held still within each run,
three 0/1 flags differed between them, and one of them, bit 0 of the word at `0x9DD130`, is read by the movie player.

- **The movie player** (`func_003F5748`, every frame) ends a movie when that bit is set and the first connected pad
  (nine entries of 400 bytes from `0x941660`) holds a face button: its buttons at `+0xB4`, masked with `0xF0`. Both pass
  to `func_002EA0D4`, the game's skip.
- **The bit** comes from `func_003F5558`, which the boot sequence calls with each movie it starts, and the sequence
  decides it from the movie's name (kept at `0x8CEC08`, `openingInt6` for this one as the scripts give it; the tests,
  `func_0052BAE4`, ignore case): never for `SMLogo`, always for `Credits` and `BTS_*`, for
  `OpeningInt6` what `func_0001B0FC` returns, and for the others the word at `0x8CF1DC`, 0 in every run here (so a face
  button never ends a level's movie; the pause menu does).
- **`func_0001B0FC`** returns the word at `0x85FEF4`, which the save code sets once `<serial>-SYSDATA` has loaded (its
  4 KB buffer is at `0x85EEF0`, set up by `func_0001ACC0`). On a first start the load finds nothing (the save callback
  returns -4, no data) and the word stays 0. So the test is whether a save was loaded, not a field in it.

The game also takes a `-skipintro` argument (`func_00367B44`, beside `-p` and `-openbeta`): it clears the byte at
`0x839D09` and sets `0xA0B111`, which steer the boot screens' loader (`IntroLoaderThread`), not this movie. Not used.

## The two patches

- **Skippable Opening Movie** (`opening_movie_skippable`, on by default): the instruction after the call of
  `func_0001B0FC` (`0x00208AE8`, a nop) becomes `li r3,1`, so the sequence takes the opening movie as skippable as on a
  later start. The save is untouched, and the other movies are decided as before.
- **Skip Opening Movie** (`skip_opening_movie`, off by default): `gowa_skip_opening_movie` (`port/movies.cpp`) runs
  before the movie player's two compares (`0x003F6A1C`, the bit; `0x003F6A8C`, the buttons) and, while the sequence's
  movie is OpeningInt6, makes both read as set: the movie ends on its first frame by the game's own skip, on a first
  start too, with the other patch on or off.

The hook tests the name without case, as the game does: its first version tested `OpeningInt6` as the ELF spells it and
never matched.

The catalog takes a patch made only of hooks now (`"hooks"`, each one in `scripts/ppu_hooks.json`); its guard is the
switch the hook reads. The Kit's table (`port/game_module.h`) has the new hook and the first patch's guard, ABI 7, and
`tests/test_game_module_hooks.py` checks the guards the lift reads as it checks the hooks. The launcher's presets are of
the picture and leave both patches as they are; `recomplauncher.json` has them as one setting, Opening movie.

## Tried

The US release, the dev build, new profiles each time:

- **A first start with the defaults** (Skippable on): Square 10 s into the opening movie ended it 0.5 s later.
- **A first start with Skip Opening Movie on and Skippable off**: the movie ended 0.5 s after it opened, with the
  `[movies]` line in the log; New Game went on to the first level, whose movie still played 12 s in, and Select opened
  the pause menu with Skip Cinematic there.
- **The next start on that profile, both on**: the opening movie ended 0.5 s after it opened.
- **The Kit** (a test package; its DLL built by `kit-build` from the packaged Kit, as on a player's PC): a first start
  with Square, and a later one with Skip Opening Movie on, the same as above.

## Not done

Ending every movie and cinematic by itself (option 3 of the first version of this note): the game's own pause menu does
it in two presses, on a first start too, and some cinematics end in play or a quick-time event.
