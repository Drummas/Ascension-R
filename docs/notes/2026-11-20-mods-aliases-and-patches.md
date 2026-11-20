# Mods: one picture for many textures, and a big file as a patch (2026-11-20)

A character mod, a new body for Kratos with its pictures, came to 343.5 MB in 40 files, 277.5 MB zipped. Two things
made it that big, neither of them the mod's own work:

| | in the mod | why |
|---|---|---|
| `textures\` | 187.3 MB, 35 files | 9 pictures: a 4096x4096 colour atlas under each of the 8 texture ids it stands for (10.1 MB each), a normal atlas under 5 (17.1 MB each), and smaller ones. PNG does not shrink in a zip, and a zip holds each file on its own. |
| `archive\WAD\PS3_BE\R_HERO00.AS` | 143.6 MB | the whole file, as `archive\` takes one: the game's is 127.1 MB, the body adds 22.6 MB (five bodies' new streams at the end, and the meshes' entries changed in place). |
| `archive\WAD\PS3_BE\R_HERO00.WAD` | 11.8 MB | the whole file again, for a few pointers changed in place. |

## One picture for many textures: aliases.txt

`textures\aliases.txt` (port/textures.cpp `read_aliases`): a line a texture, its id and then the picture, the id of
one in the folder or its file by its path there. A picture only the list names can have any name that ends in
`.png`. A texture the folder has a picture of its own for keeps it; a line whose picture is not in the folder, or is
outside it (`..`, a drive), is left out and counted, and the log names the first. Each mod's pictures and aliases are
gathered on their own and then put under the mods above it, so the first mod still wins whichever way it gives a
texture a picture. The Mods tab and the `[mods]` line count the lines: `textures: 9 pictures, 26 more by aliases.txt`.

The pictures were already read and uploaded once for all the textures that share them (the decode keyed by the file's
content, 2026-11-20); the list only stops the mod from holding them again. `scripts/modtools.py textures` folds the
files that are one file, byte for byte, into the list: the first by name stays (the one the game takes when two files
name one id), the others' files go.

## A big file as a patch: the game's own .PATCH

The game looks for `<file>.PATCH` as it loads a WAD, a `.TS` or a `.AS` file, and puts the newest one it finds over
the file from its base archives ([note](2026-11-18-mods-archive-and-text.md)). Its updates bring 479 of them. Their
form, version 4: `u16` version, `u16` n, n steps of (`u32` from, `u32` length), then the patch's own data. A step with
the top bit of `from` set takes `length` bytes of the patch's own data at the offset the other bits give; any other
takes them from the base file at `from`. The file is the steps' bytes one after the other. The updates' own patches use
all of it: `BOGARENA.WAD.PATCH` in `TPPS5.PSARC` has 1,298 steps, 465 of them its own data, the others ranges of the
base in any order (`(0, 3504)`, then 64 own bytes, then `(3568, 64)`, skipping 64 of the base). Of the patches in
`TPPS1`, `TPPS4` and `TPPS5`, 117 have one step of their own data, 9 none at all, and the rest from 2 to 1,006.

So a mod's `.PATCH` can be made against the game's file and the game does the rest; `archive\` already took a mod's
own `.PATCH` as it is. What it lacked was a way to make one, and a guard: a patch takes ranges of the file it was made
for, and put over another copy (another release's disc, a file an update changed) it gives garbage where the game
expects a mesh.

- **`scripts/modtools.py patch <the mod's whole file> <entry> <archive folder>`** reads the game's file the way the
  game finds it (the newest update that brings it whole, else the disc's archive that has it), compares the two at the
  same place in blocks of 4 KB and, where a block differs, in pieces of 64 bytes; a piece in common becomes a step
  from the game's file (runs joined), the rest the patch's own data (a stretch in common shorter than 32 bytes between
  two own pieces goes in with them). Past 65,535 steps (the count is a `u16`) it takes pieces four times as big. It
  puts the patch over the game's file itself and compares the result with the mod's file before it writes anything.
  It does not look for data the mod moved: that goes in as the patch's own.
- **`<entry>.PATCH.base`** beside it: `entry`, `size` and `sha1` of the game's file. `scripts/modpack.py` reads the
  same file the same way when it packs (the launcher now gives it the disc's `USRDIR`, `disc` in `input.txt`) and
  leaves the patch out when the size or the SHA-1 is another's, with an `error` line that the Mods tab shows: `not
  packed: R_HERO00.AS.PATCH: made for another copy of the file (its SHA-1 differs)`. The `.base` is never packed and
  not counted as an entry. A `.PATCH` without one goes in as before.

For the body above: `R_HERO00.AS.PATCH` 98 steps, 121.1 MB from the game's file and 22.6 MB of its own, a 22.6 MB file;
`R_HERO00.WAD.PATCH` 11 steps, 476 bytes. Each made in about 1.3 s.

## The result

The same mod with both: 55.8 MB in 17 files (9 pictures and `aliases.txt`, the two patches and their `.base`, the
two DCB files whole), from 343.5 MB in 40.

- **The pack**, as the game starts: `TPPS6.PSARC: 4 entries, 14.7 MB, in 0.2 s`, `[mods] pack: one more update
  (1.1 s)` with the two `.base` checks (each reads the file out of `RESOURCES.PSARC`); made again only when the mods
  change, as before.
- **The log**: `[tex] 9 pictures of mods (26 more textures by aliases.txt), 0 of the Xbox button icons, for 56
  textures (21 of them other copies of the game's)`, the same 56 textures as with the 35 files.
- **The game**, one run each, screenshots set beside the ones of the mod with whole files: the bench route's
  checkpoint with the hero turned to the camera (+30 s), and a later chapter's save (Chapter 5, the Village of Kirra,
  where the game draws the body that is not the prison's) replayed from its recorded pad at 110 s. The same pictures,
  and no null access in either log.

## The tests

- `tests/test_modtools.py` (CI): a patch made and put over its file again (in place, shorter, longer, the same,
  empty), its own steps in order, too many places taking bigger pieces, a patch that reads past a file refused, the
  `.base` text; the game's file found in the newest update before the disc; the command on a made-up game folder; the
  folding of pictures into `aliases.txt` (a dry run, a second file for one id left alone, a picture not named by an
  id, the list's own lines kept).
- `tests/test_modpack.py` (CI): a patch with its `.base` packed for that copy of the file, left out for another with
  the reason, its file found in an update before the disc, a file the game does not have; the `.base` never packed.
- `tests/test_textures.py` (CI): aliases by id and by path, a picture of its own winning, lines left out and the
  log's line, a mod above winning over a mod's own picture.
- `tests/test_mods.py` (CI): a `.base` not counted as an entry; a mod with only `aliases.txt` not empty, and its count
  in the summary.
