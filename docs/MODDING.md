# Making mods for Ascension-R

A mod is a set of files that the game reads in place of its own, or beside them. Ascension-R takes them from the
`mods` folder, and the launcher's **Mods** tab lists them. The game's own folder is never changed, and no part of a
mod runs as a program.

## Where mods go

- `mods\` beside `Ascension-R.exe`, or `build\mods\` in a build from source. `[mods] folder` in the settings names
  another one. The Mods tab's **Open folder** makes the folder if it is not there yet.
- One folder or one `.zip` for each mod. A new one shows on the Mods tab, switched on, at the end of the list.

## A mod's layout

```
MyMod\
  mod.ini            its name, version, author and a line about it (it can do without one)
  files\             laid out as the game's USRDIR folder is
    PATCHES          stands for USRDIR\PATCHES
    TPPS6.PSARC      stands for USRDIR\TPPS6.PSARC
    data\fonts\...   stands for USRDIR\data\fonts\...
  archive\           files inside the game's archives (below)
  text\              lines of the game's text (below)
  textures\          pictures in place of the game's textures (below)
  proportions\       other bone lengths for Kratos (below)
```

- A file there is read in place of the game's file of that name, or added where the game has none. Names match
  without regard to case.
- Mods made for RPCS3 come laid out like the PS3's paths, and are taken as they are: `dev_hdd0\game\<id>\USRDIR\`,
  `USRDIR\` or `PS3_GAME\USRDIR\` work as `files\` does. So does a folder that has the files right in it, beside a
  read-me.
- One mod serves every release the port takes. The digital release reads its files from
  `/dev_hdd0/game/NPUA80918/USRDIR`, a disc from `/dev_bdvd/PS3_GAME/USRDIR` and its update from
  `/dev_hdd0/game/<id>/USRDIR`, and `files\` stands for each of them. It does not stand for the game data folder
  (`/dev_hdd0/game/<id>-DATA`), which has a USRDIR of its own.
- Folders are not merged: when the game lists a folder, it sees its own files only. It opens its files by name, as
  `ARCHIVES` and `PATCHES` list them, so this does not stop a mod.

## mod.ini

```ini
[mod]
name = Readable name
version = 1.0
author = Who made it
description = A line about what it changes.
```

In UTF-8. Every key is optional. Without a name, the folder's name, or the zip's, is the mod's name. The tab shows two
lines of the description at most.

## A .zip

- It is unpacked once into `mods\.unpacked\<name>.zip\`, and again when its size or time changes. If it holds a single
  folder, the mod is that folder, so a zip of `MyMod\` works as `MyMod\` does.
- Stored or Deflate. It must not be encrypted, a Zip64 file (over 4 GB, or over 65,535 files) or a zip in several
  parts, and none of its names may lead out of its folder. Such a zip shows on the tab with what is wrong with it.

## The order

- The first mod in the list wins where two mods have the same file. The tab says how many of a mod's files a mod above
  it has too, and which one.
- The settings keep the list: `[mods] order = A|B|C` (the names in the folder), `off = B` (the ones switched off) and
  `use = on` (**Use mods**: off leaves every mod out).

## Files inside the archives: archive\

The game's data is in PSARC archives, the ones `ARCHIVES` names (`GAME.PSARC`, `SHELL.PSARC`, `RESOURCES.PSARC` and
others), and its updates, `TPPS.PSARC` and `TPPS1.PSARC` to `TPPS5.PSARC` (`PATCHES` holds `5`). A mod's `archive\`
has files for entries of the archives, by their names there:

```
MyMod\
  archive\
    WAD\PS3_BE\SHELL.WAD       stands for /WAD/PS3_BE/SHELL.WAD
    DC\PS3_BE\WAD_X.DCB        stands for /DC/PS3_BE/WAD_X.DCB
```

As the game starts, the archive files and text lines of every mod that is on go into one more update, made by the
Kit's Python (`modpack.py`): `TPPS6.PSARC`, with `PATCHES` holding `6`, in `mods\.built\`. The game reads it before
any mod's own files. It is made again only when a mod's archive or text files, the list's order or the game's updates
change; the Mods tab says what the last start made of each mod.

- **A WAD, a `.TS` or a `.AS` file that the game's updates change** goes in as a `.PATCH` of one step: the game puts
  the newest `.PATCH` of a file over the base, so this one gives the mod's file as it is. A whole file in the update
  would not do: the game would put the older update's `.PATCH` over it, and the EU disc hangs at its load then
  ([note](notes/2026-11-18-mods-archive-and-text.md)).
- **Any other file** goes in whole, as the game's own updates bring its DCB files. A file the archives do not have is
  added.
- **A `.PATCH` of the mod's own** goes in as it is. With a `<name>.PATCH.base` beside it, only for the copy of the
  game it was made for: see below.
- Names are taken in upper case, as the archives have them. `desktop.ini`, `Thumbs.db` and files whose name starts
  with a dot are left out.
- The first mod in the list wins where two have the same file.

**Only what the mod changes: a `.PATCH`.** A mod that changes part of a big file need not bring it whole: Kratos's
`R_HERO00.AS` is 127 MB, and a new body for him changes 23 MB of it. The game puts a `.PATCH` over its own file as it
loads it, the way its updates change their WADs, so a mod can bring that instead:

```
python scripts\modtools.py patch <the mod's whole R_HERO00.AS> WAD/PS3_BE/R_HERO00.AS MyMod\archive
```

writes `MyMod\archive\WAD\PS3_BE\R_HERO00.AS.PATCH` and `R_HERO00.AS.PATCH.base` (the Kit's Python is
`kit\python\python.exe`, its scripts `kit\scripts\`). The patch takes the ranges the mod's file has at the same place
as the game's from the game's, and the rest from its own data: the body above is a 22.6 MB patch, the WAD that goes
with it, 11.8 MB whole, 476 bytes. The script reads the game's file from the newest update that brings it whole, else
from the disc's archives (`--game` names the disc's `PS3_GAME` folder, `--updates` the updates' `USRDIR`), and checks
that the patch gives the mod's file back before it writes it.

- **The `.base`** names the game's file the patch was made for: its size and SHA-1. As the game starts, the packer
  checks it against the game's own file, the one the patch would go over, and leaves the patch out when it is
  another (another release's disc, an update that changed it): the patch's ranges would be taken from the wrong
  places. The Mods tab says so: `not packed: R_HERO00.AS.PATCH: made for another copy of the file`. The `.base` itself
  never goes into the game.
- **What the patch holds**, in the form the game's updates bring theirs (version 4): `u16` version, `u16` n, n steps of
  (`u32` from, `u32` length), then the patch's own data. A step with the top bit of `from` set takes `length` bytes of
  the patch's own data, from the offset the other bits give; any other takes them from the game's file at `from`. The
  file is the steps' bytes, one after the other. The script only finds what is at the same place in both; data the
  mod moved goes into the patch whole.
- A patch is put over the game's file, never over another mod's: two mods with a patch of the same file are not
  added together, the first one wins.

A mod that brings an update of its own in `files\` (a `TPPS6.PSARC` and `PATCHES`, as `gowa.py text build` made them
before) still works: the launcher's update comes after it (`TPPS7.PSARC`), and wins where both change the same file.

## The game's text: text\

A mod's `text\` has lines of the game's text, in the form `gowa.py text export` writes: `<id>.<k><TAB><text>`, a line
for each line of text, as many as the mod changes. A file is for the language its name or its folder's starts with:

```
MyMod\
  text\
    en.tsv            English
    en-gb-story.tsv   English (UK) alone
    fr\menus.tsv      French
```

The languages are the game's: `en`, `en-gb`, `fr`, `es`, `es-la`, `de`, `it`, `nl`, `pt`, `pt-br`, `ru`, `pl`, `tr`,
`el`, `ja`, `ko`, `zh`.

- **English** is two languages to the game: `EN`, the digital release's, and `EN-GB`, the EU disc's. An `en` file is
  both, unless the mod has an `en-gb` file too. A line the UK English lacks is skipped there.
- **Each line is checked** as `gowa.py text build` checks a translation: the `[..]` tokens kept, not empty, a key the
  game has, no character the English never uses (the font may lack it). A line that fails is left out, and the tab says
  how many were, and why the first one was. `gowa.py text build` says it of every line at once, for the one who writes
  them.
- The first mod in the list wins where two have the same line.
- Both of the language's files get the lines, `R_LANG_<lang>.WAD` and its multiplayer one, made from the game's
  newest.
- A mod whose `archive\` brings a language's whole `R_LANG_<lang>.WAD` comes first: the text lines for that language
  are left out, and the tab says which mod brings it.

## Pictures in place of the game's textures: textures\

A mod's `textures\` has PNG files, each named by the id of the texture it stands for: sixteen hex digits, the same
in every release and from run to run.

```
MyMod\
  textures\
    2133aab0625680af.png                    in that texture's place, at any size
    1f52688dc50e2bfb_64x64_88.overlay.png   drawn over the game's own texture
```

- **The ids come from the dump.** Mods tab, **Write out the game's textures**: as the game plays, each texture it
  loads goes once into `textures-dump\` beside the settings (beside `Ascension-R.exe` in a release, `build\` in a
  build tree), as `<id>_<width>x<height>_<format>.png`. Copy one into a mod's `textures\`, change it, and keep the id
  at the start of its name: anything after an `_` is free. The game is slower while the dump is on.
- **A picture** (`<id>.png`) goes in the texture's place. It can be of any size; the mip levels are made from it.
- **Size and memory.** A picture goes to the GPU uncompressed, 4 bytes a texel with its levels: 85 MB for 4096x4096,
  21 MB for 2048x2048, where the game's own textures are compressed and smaller. The textures held at once share a
  third of the card's memory, at most 2 GB; past that the game's are let go and loaded again, which stutters. One
  picture for many textures (an atlas for a whole character, through `aliases.txt` or the same file under each
  texture's name) is read once and held once for all of them, so pictures that repeat cost nothing more; keep each
  picture about the size its texture needs on screen.
- **One picture for many textures: `aliases.txt`.** A character's atlas stands for each texture of the character, and
  a file of it under each texture's name makes the mod as big again for every one (8 copies of a 10 MB atlas). The
  folder's `aliases.txt` gives more textures a picture the folder has, one a line: the texture's id, then the picture,
  either the id of one in the folder or its file by its path there. A picture only the list names can have any name
  that ends in `.png`. A line that starts with `#` is a comment.

  ```
  # <texture id> <the picture it takes>
  0b0c9bbf4142f441 127490984add5370
  12fd992d99d6d6ed atlas\body.png
  ```

  A texture the folder has a picture of its own for keeps that one. A line whose picture is not in the folder, or
  outside it, is left out, and the log says how many were and why the first one was. `python scripts\modtools.py
  textures MyMod\textures` folds the pictures that are one file, byte for byte, into the list: the first by name
  stays, the others' files go.
- **Copies.** The game keeps many textures in more than one copy: whole, in an archive's stream or a WAD, and in a
  level's WAD as their levels from level 2 down, which it draws with as a texture of their own size until the whole
  one has streamed in (in some cinematics, all along). Each copy has its own id; a picture for any of them goes in the
  place of all of them, and a smaller copy gets it smaller by as much: a 2048x4096 texture's 512x1024 copy takes a
  4096x4096 picture at 1024x1024. A copy with a picture of its own keeps that. The copies are listed in
  `port/texture_copies.inc`, which `scripts/texture_copies.py` makes from the game's archives.
- **An overlay** (`<id>.overlay.png`, or `<id>_anything.overlay.png`) is drawn over the game's own texture, which is
  first scaled to the overlay's size: where the overlay's alpha is above 1 it is laid over, where it is 1 the texel is
  made clear, and where it is 0 the game's shows. So a mod need hold none of the game's own pictures.
- **Formats.** The game's colour textures (A8R8G8B8, the 16-bit ones, DXT1/3/5) take a picture as RGBA; its
  one-channel and two-channel ones (B8, X16, G8B8) take a picture's red (and green) channel. A cube map or a volume is
  not named. A texture that changes as the game runs (a copy of the frame, a video) stops being looked up after four
  changes; the game's font pages are made as it runs, so their ids are not the same from one run to the next.
- The first mod in the list wins where two have a picture for the same id. A file that is not a PNG Windows can read
  is named in the log once and left out.
- The id is XXH64 of the texture's level 0 as the game has it, with the format, width and height in the seed
  (ps3recomp's `libs/video/rsx_tex_replace.h`).

**Xbox button icons** is a mod of this kind that comes with the port (`optional mods\Xbox button icons` in the
download, `optional-mods/` in the tree): A, B, X and Y in place of Cross, Circle, Square and Triangle, and View for
Select, each picture named by its texture's id and the button's name. It is off until it is copied into the mods
folder; a mod above it with a picture of the same texture wins.

## Other bone lengths: proportions\

The game takes the length of each bone from its animations, not from the skeleton in the archive, so a character
whose mesh is made for longer legs or a shorter neck still moves with Kratos's. A mod's `proportions\` changes the
lengths: each bone keeps the direction the animation gives it, and its length is the animation's times the mod's
ratio.

```
MyMod\
  proportions\
    heroA.bin       Kratos's whole skeleton, where the animation puts it together
    81BC3F6F.bin    or the meshes of one body skeleton alone
```

- **Make the files with `scripts/proportions.py`** and a JSON file of the ratios by joint name. The script's help has
  the rest.
- **A ratio belongs to the joint at the bone's end**: it scales the joint's distance from its parent. A shorter
  forearm is the wrist's ratio, a shorter upper arm the elbow's (`JOLeftLowerArm1`). The joints below it move with it.
  A joint may have three, `[x, y, z]`, one for each of its offset's axes in its parent's (with `"where": "animation"`
  and `--binds`): the blades on the back (`rightBladeBack`, `leftBladeBack` and the holsters, under `JOBack3`)
  brought in to a slimmer back, less behind than across.
- **The whole skeleton**, `"where": "animation"`, from `R_HERO00.WAD`, whose template skeleton `heroA` the animation
  uses for every form of Kratos: `{"heroA": {"where": "animation", "ratio": {"JOLeftWrist1": 0.8, "JORightWrist1":
  0.8}}}`. The lengths change where the hero's animation job puts the joints together, so whatever follows a joint
  follows them: the skin of every body and costume, the blades in the hands and on the back, the chains, the effects.
  The game may read joint positions for play too, so a shorter arm may reach a little less.
- **A mesh modelled for the new lengths** needs the inverse binds of its rest pose, or the animation pulls it out of
  shape as it does Kratos's own. `proportions.py --binds R_HERO00.AS spec.json R_HERO00.new.AS` writes them into the
  body skeletons the spec names, with the same ratios; the mod brings that archive (or a patch of it,
  `scripts/modtools.py patch`). The game draws Kratos's body with one of five skeletons: `81BC3F6F`, `4E90421D`,
  `34AE727F`, and from the Village of Kirra on `9DB18EF1` and `58EDB2C7`.
- **One body's meshes alone**, `"where": "skinning"` (the default), from `R_HERO00.AS` by the skeleton's name: only the
  skin of the meshes of the sizes the file names changes (by default the skeleton's own meshes), on the skinning jobs.
  The weapons and anything the game places by a joint stay where Kratos's would be, and the Grotto's skinned meshes,
  which the game builds another way, are drawn as they were. A mesh bound to a skeleton of the new lengths gives its
  inverse binds in the JSON.
- The files' forms are described in `port/skel_prop.c` and `port/edge_prop.c`; how the animation job was found is in
  `docs/notes/2026-11-21-hero-skeleton-job.md`.

## What this build does not read yet

A mod can have this folder, which a later Ascension-R may read. The tab names it, and this build leaves it out:

| folder | what it is to hold |
|---|---|
| `patches\` | patches to the game's code, in RPCS3's `patch.yml` form |

## Checking a mod

- The log, `logs\session-*.log` beside the exe (`build\logs\` in a build tree), has a `[mods]` line with each mod and
  what it gave, `[mods] pack:` when the update was made or why it was not, and `[fs] mod '<the game's path>' ->
  '<the file>'` for each file taken, the first 64 of them.
- `mods\.built\` holds the update the last start made, `result.txt` (what each mod gave) and `pack.log` (what the
  packer said).
- A `[tex]` line says how many pictures the mods have (and how many more textures their `aliases.txt` give them), for
  how many textures, and how many of those are other copies of the same textures of the game's; each texture given
  one is named, `[tex] <id> <width>x<height> fmt <format>: a picture in its place`, the first 32 of them. A mod whose
  `aliases.txt` has lines that were left out gets a line of its own: `[tex] MyMod: aliases.txt: 2 lines not taken;
  line 5: no picture of 00000000000000ff in the folder`.
- `[props]` lines name each proportions file read (`<file>: a skeleton of <n> joints, <k> of them another length (at
  the animation)`, `<file>: <n> joints, for meshes of <size> bytes`) or turned away; `heroA.bin: 261 joints take the
  new lengths where the animation puts them together` when the game first animates Kratos with them, and each mesh
  that takes a skinning file when the game first draws it.
- **Report a problem** puts the same `Mods:` line in the report's notes, without the folder's path.
