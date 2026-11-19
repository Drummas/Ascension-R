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
  proportions\       other bone lengths for a character's meshes (below)
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
- **A `.PATCH` of the mod's own** goes in as it is.
- Names are taken in upper case, as the archives have them. `desktop.ini`, `Thumbs.db` and files whose name starts
  with a dot are left out.
- The first mod in the list wins where two have the same file.

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

**Button icons** (Controls tab) puts Ascension-R's own Xbox icons in place of the game's PlayStation ones: A, B, X
and Y where Cross, Circle, Square and Triangle are, and View for Select, as a set of pictures like a mod's. A mod's
picture of the same texture wins over them.

## Other bone lengths: proportions\

The game takes the length of each bone from its animations, not from the skeleton in the archive, so a character
whose mesh is made for longer legs or a shorter neck still moves with Kratos's. A mod's `proportions\` changes the
lengths as the game draws: each bone keeps the direction the animation gives it, and its length is the animation's
times the mod's ratio.

```
MyMod\
  proportions\
    81BC3F6F.bin    one file a skeleton, named after it
```

- **Make the files with `scripts/proportions.py`**, from the archive that has the skeleton and its meshes (the game's
  `R_HERO00.AS` for Kratos's body, or the mod's own when it brings meshes) and a JSON file of the ratios by joint
  name, `{"81BC3F6F": {"ratio": {"JOLeftWrist1": 0.8, "JORightWrist1": 0.8}}}`. The script's help has the rest:
  which meshes, by their sizes, and the inverse binds of a mesh bound to a skeleton of other lengths.
- **A ratio belongs to the joint at the bone's end**: it scales the joint's distance from its parent. A shorter
  forearm is the wrist's ratio, a shorter upper arm the elbow's (`JOLeftLowerArm1`). The joints below it move with it.
- **The meshes it changes** are the ones of the sizes the file names (by default the skeleton's own meshes in the
  archive); a mesh of another size is drawn as it was. The game draws Kratos's body with one of three skeletons
  (`81BC3F6F`, `4E90421D`, `34AE727F`), so a mod gives all three.
- **Inverse binds.** With the skeleton's own (the default), the mesh's skin goes where the bones go. A mesh bound to
  a skeleton of the new lengths gives its inverse binds in the JSON, and is then drawn as it was made.
- What is not changed: the weapons and anything the game places by a joint of its own (the blades on the back stay
  where Kratos's would be), and the Grotto's skinned meshes, which the game builds another way.
- The lengths are made each frame on the skinning jobs (`native/spu_edge_prop.c`); the file's form is described
  there.

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
- A `[tex]` line says how many pictures the mods have, for how many textures, and how many of those are other copies
  of the same textures of the game's; each texture given one is named,
  `[tex] <id> <width>x<height> fmt <format>: a picture in its place`, the first 32 of them.
- `[props]` lines name each proportions file read (`<file>: <n> joints, for meshes of <size> bytes`) or turned away,
  and each mesh that takes one when the game first draws it.
- **Report a problem** puts the same `Mods:` line in the report's notes, without the folder's path.
