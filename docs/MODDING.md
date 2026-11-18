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

## Changing what is inside the archives

The game's data is in PSARC archives, the ones `ARCHIVES` names (`GAME.PSARC`, `SHELL.PSARC`, `RESOURCES.PSARC` and
others), and its updates, `TPPS1.PSARC` to `TPPS5.PSARC` (`PATCHES` holds `5`). For a WAD, the game takes the
`.WAD.PATCH` of the newest update that has one. So a translation is a sixth update: `TPPS6.PSARC` with the text patches,
and `PATCHES` holding `6` ([note](notes/2026-11-11-game-text.md)). `gowa.py text build` makes it as a mod,
`build\mods\translation\`.

Two mods that each bring a `TPPS6.PSARC` cannot both be that update: the first one in the list wins, and the tab says
so. A later Ascension-R is to put several mods' entries into one update itself (the `archive\` folder below).

## What this build does not read yet

A mod can have these folders, which a later Ascension-R is to read. The tab names them, and this build leaves them out:

| folder | what it is to hold |
|---|---|
| `archive\` | files inside the archives, by their names there (`archive\WAD\PS3_BE\SHELL.WAD`), packed into an update by the launcher |
| `textures\` | pictures put in place of the game's as they reach the graphics card, by a hash of the game's picture |
| `text\` | lines of the game's text, in the form `gowa.py text export` writes |
| `patches\` | patches to the game's code, in RPCS3's `patch.yml` form |

## Checking a mod

- The log, `logs\session-*.log` beside the exe (`build\logs\` in a build tree), has a `[mods]` line with each mod and
  its files, and `[fs] mod '<the game's path>' -> '<the file>'` for each file taken, the first 64 of them.
- **Report a problem** puts the same `Mods:` line in the report's notes, without the folder's path.
