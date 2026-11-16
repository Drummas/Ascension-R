# Plan: the EU disc (and the other versions) from start to finish (2026-11-17)

Issue #4 asks for the EU disc, BCES01741; one comment for the US disc, BCUS98232. What is known is in
[the EU disc against our GOWA.elf](2026-11-17-eu-disc-gowa-self.md): at 1.12 the EU game's `GOWA.elf` is ours byte
for byte, so the game's code, the Kit's DLL, the hooks, the patches and the native SPU work stay as they are. This plan
is everything else: the disc layout, the launcher, decrypting an EU copy without keys, the files that name NPUA80918,
tests, and the release. About five to seven days of work; the user's EU copy on this PC lets every step be tested here.

## Goals and what is out

- **In:** BCES01741 at 1.12, from an extracted disc (or RPCS3's disc folder) and RPCS3's update folder, found,
  decrypted, built and played from the launcher as NPUA80918 is; its ten languages; its saves.
- **Then, cheaply, from the same work:** BCUS98232 (same layout; needs one check of its 1.12 `GOWA.elf`), other disc
  SKUs the ELF names (BCES01742, BCES01838, BCJS37008, BCAS25016) once someone checks one, NPEA00445 (EU digital,
  a `.rap` like NPUA80918) once someone checks it.
- **Out for now:** encrypted (Redump, not decrypted) ISOs; moving saves between regions; reading ISOs directly (Phase 8).

## What is known (all measured on the user's copy)

| | NPUA80918 (US digital) | BCES01741 (EU disc) |
|---|---|---|
| base files | `dev_hdd0/game/NPUA80918/USRDIR` | the disc's `PS3_GAME/USRDIR` (extracted, or RPCS3's `games.yml` names the folder) |
| update to 1.12 | in the same folder | `dev_hdd0/game/BCES01741` (RPCS3 installs the PKGs A0104 to A0112 there) |
| executable | `USRDIR/GOWA.SELF`, started by a 71 KB `EBOOT.BIN` | the same two files, from the update folder |
| `GOWA.SELF` license | NPDRM local: the `.rap` | NPDRM free: a KLIC held in plain bytes in the 71 KB `EBOOT.BIN` |
| `GOWA.elf` 1.12 | `4bf75c89...62b5` | the same file |
| PARAM.SFO | HG | disc DG 01.00; update GD, APP_VER 01.12 |
| saves | `BCUS98232-*` | `BCES01741-*` (`-SYSDATA`, `-PROFDATA-n`) |
| game data | `NPUA80918-DATA` | `BCES01741-DATA` (0.1 MB) |
| languages | English, French, LA Spanish, BR Portuguese | English, French, Spanish, German, Italian, Portuguese, Russian, Polish, Turkish, Greek |
| patch archives | `TPPS*.PSARC`, `PATCHES` | the same scheme, EU languages (`TPPS-GERMAN`, ...) |

- The runtime already boots a disc game: `cellGame_init_from_paramsfo` reads `<vfs>/PS3_GAME/PARAM.SFO`, CATEGORY DG
  gives the disc type and `/dev_bdvd/PS3_GAME` paths, and `/dev_bdvd/` maps to `paths.vfs`.
- **Decrypting without keys works.** `rpcs3 --decrypt` opens the update's `EBOOT.BIN` with no key (free license). Of
  its file-backed data, the 8-aligned 16-byte windows that look like a key (12 or more different bytes, at most 10
  printable) are 2; given to `rpcs3 --decrypt GOWA.SELF` on standard input (it asks `Enter KLIC` and reads stdin, not
  the console), the second one opened it in 0.8 s and the result was `4bf75c89...`. No key is in the port; the key is
  read from the player's own `EBOOT.BIN` each time, as RPCS3 itself learns it when the game runs.

## Phase 1: the EU game runs from a layout made by hand (1 day)

Prove the game itself before building the launcher around it. Dev build, a test hdd0, nothing of the player's written.

- A test setup: `paths.vfs` = the extracted disc (`E:\PS3\Games\BCES01741`), `paths.hdd0` = a new test hdd0 whose
  `game\BCES01741` is a junction to `E:\PS3\rpcs3\dev_hdd0\game\BCES01741` (removed as a link after), `PS3_TITLE`
  BCES01741, `PS3_BOOT_PATH` `/dev_hdd0/game/BCES01741/USRDIR/GOWA.SELF`.
- `port/main.cpp`: take `PS3_TITLE` from the vfs PARAM.SFO's TITLE_ID and build the boot path from it (both kinds
  boot `/dev_hdd0/game/<id>/USRDIR/GOWA.SELF`), instead of the NPUA80918 constants; `game_open_failed` checks
  `/dev_bdvd/PS3_GAME/` and `/dev_hdd0/game/<id>/`.
- `cellGame.c`: for a disc game with an update, APP_VER and VERSION from the update's PARAM.SFO (`/dev_hdd0/game/<id>/
  PARAM.SFO`, 01.12), as the PS3 reports them; CATEGORY and TITLE_ID stay the disc's. Check what the game asks
  (`cellGamePatchCheck` answers "not a patch", as it should for a booted title).
- Watch the log for: the update's `PATCHES` and `TPPS*` opened from `/dev_hdd0/game/BCES01741/USRDIR`, the base
  archives from `/dev_bdvd`, `BCES01741-DATA` made, saves as `BCES01741-*`, no failed opens.
- **Done when:** title screen, a new game through the opening chapter's first fight, a save made and loaded after a
  restart, the game in French and in German (`system.language`), screenshots clean.

## Phase 2: one table of titles (1 day)

Replace the single title with a table, so every place that says NPUA80918 asks it instead.

- `port/game_title.h` (new): for each known title, its id, kind (digital or disc), where the update lives, the
  license (`.rap` name, or the KLIC from `EBOOT.BIN`), save prefix, the file list to check, and whether it is enabled:
  NPUA80918 (on), BCES01741 (on after Phase 1), BCUS98232, NPEA00445 and the other disc ids (off until checked).
- The places: `game_find.cpp` (`k_title_id`, `k_title_dir`, the folder candidates), `game_prepare.cpp`
  (`k_rap_name`), `launcher.cpp` (texts that say "This port runs NPUA80918 1.12", the game row), `main.cpp`,
  `precompile.cpp` (the archive folders: the update's `USRDIR`, then the disc's), `scripts/gowa.py` (`TITLE_ID`,
  `game-files`, `kit_train`'s junction, `--game-dir`), `scripts/gametext.py` (the mod folder `dev_hdd0/game/<id>`).
- The chosen title lands in the settings (`[game] title`), written by the launcher with the paths.
- **Done when:** NPUA80918 behaves exactly as before (tests, a bench run, the Kit's DLL hash unchanged) and the
  Phase 1 setup runs from settings alone.

## Phase 3: the launcher finds an EU install (1 to 1.5 days)

- **From RPCS3:** `config/games.yml` names each disc's folder (`BCES01741: E:/PS3/Games/BCES01741/`), and the same
  RPCS3's `dev_hdd0/game/BCES01741` holds the update. `game_search` already visits RPCS3 folders; read `games.yml`
  there and in `%APPDATA%\rpcs3`.
- **From the disks:** a folder with `PS3_GAME/PARAM.SFO` saying BCES01741 and DG is a disc; its update is looked for
  in every RPCS3 found. **Browse** takes either folder and finds the other.
- **States the game row says:** found and 1.12; disc without update ("install updates 1.04 to 1.12 in RPCS3"); update
  older than 1.12; disc files missing (the file list, Phase 5); only an ISO ("extract it: right-click, Mount, copy
  everything to a folder", until Phase 8); an encrypted ISO or folder (the PSARCs do not start with `PSAR`: "not
  decrypted, not supported").
- **Links, as for NPUA80918:** `<vfs>\PS3_GAME` to the disc's `PS3_GAME`, `<hdd0>\game\BCES01741` to the update
  folder; both only read. A PC with two versions: the row lists both and the player picks.
- **Done when:** a new portable Kit on this PC finds the EU install by itself (through `E:\PS3\rpcs3`) and by Browse to
  either folder, and each wrong state above, made in a test folder, shows its message.

## Phase 4: decrypting an EU copy without keys (1 day)

`game_prepare.cpp`, for a disc title:

1. Copy the update's `EBOOT.BIN` and `GOWA.SELF` to the work folder (never write beside the game or in RPCS3).
2. `rpcs3 --decrypt EBOOT.BIN`: free license, no key.
3. From `EBOOT.elf`, the KLIC candidates (rule above), kept in memory and in a stdin file inside the work folder only.
4. `rpcs3 --decrypt GOWA.SELF` with the candidates on standard input; the result must hash to `4bf75c89...`.
5. If none fits: every 8-aligned window of the data (about 9,000 here; a few seconds), then the RPCS3 log
   (`log/RPCS3.log`, `RPCS3.log.gz`, the KLIC beside `drm_path=".../GOWA.SELF"`) if the player has started the game
   in that RPCS3, then a message asking them to start it once in RPCS3 and press **Try again**.
6. Remove the work folder; log the step's result, never a key or a candidate.

- Same RPCS3 handling as now: `RPCS3_CONFIG_DIR` at a folder of ours, the downloaded RPCS3 or the player's.
- **Done when:** on this PC, from a clean Kit, the EU copy is decrypted with no player step, the DLL the Kit builds is
  `f317f78f...` (the same as from NPUA80918), with RPCS3 0.0.43-20572 and -20607 and the one the launcher downloads.

## Phase 5: everything else that knew one title (1 day)

- **The file check:** `port/game_files.inc` gets a BCES01741 list, the disc's 1.00 files and the update's 1.12 files,
  names, sizes and the SHA-256 of their first and last 64 KiB, made by `gowa.py game-files --title BCES01741` from the
  user's copy. ISO9660 names write `-` as `_`; the list uses the real names (`MP-ENGLISH.PSARC`).
- **Shader precompile:** archives from the update's `USRDIR` and the disc's; the vertex pass should find what it finds
  for NPUA80918 (the same shaders but for language files).
- **Game text and mods:** `gowa.py text` for the EU languages (`R_LANG_<language>.WAD` from `TPPS<n>`, the same
  `PATCHES` scheme); mods under `dev_hdd0/game/<id>`.
- **Optimise for this PC:** `kit_train` links the player's disc and update the way Phase 3 does, in its own hdd0.
- **Language:** the EU languages are all PS3 system languages but Greek, which the PS3 never had: find how the game
  picks `GREEK.PSARC` (a region rule or its own menu) and say so in the launcher if it cannot be chosen.
- **Reports:** the zip says which title and version, and which update folder.
- **Done when:** precompile, a text export of the German text, a training run and a report all work on the EU copy.

## Phase 6: tests (0.5 to 1 day)

- `tests/test_game_find.py`: EU layouts made in a temporary folder (disc DG 01.00 + update GD 01.12; no update; old
  update; ISO only; an encrypted file), `games.yml` read, two versions on one PC.
- A test for the candidate rule on a made-up ELF (the windows it keeps and drops), and that no candidate or key is
  printed.
- `tests/test_kit_paths.py` and the others still pass; `check_repo.py`.
- **On this PC, end to end:** a fresh portable Kit in `dist/test/eu-run`; find, decrypt, build, precompile, play the
  opening chapter, save, quit, load, French and German, a report; then the same Kit on NPUA80918, and the fight bench
  once (expect the same 29 to 31.5 flips/s on six cores).

## Phase 7: documents and the release (0.5 day)

- README (what you need: a table of versions, ✅ NPUA80918, ✅ BCES01741, ❓ BCUS98232 and the rest), the Kit's
  `packaging/README.txt`, the site page, the launcher's help texts.
- Release notes (0.1.0-alpha.14): "EU disc supported", how to install its updates in RPCS3, ISO extraction steps.
- The reply to #4, after the user's OK: what is supported, the steps, a request for testers with BCUS98232 and other
  versions (their launcher's report says the `GOWA.elf` hash).

## Phase 8: later, each on its own

- **BCUS98232:** the user plans to get a copy; check its 1.12 `GOWA.elf`, add its file list, turn it on.
- **NPEA00445 (EU digital) and the other disc ids:** turned on when a player's report shows `4bf75c89...` and the
  layout works.
- **ISOs without extracting:** a decrypted ISO read in place (ISO9660 with multi-extent files over 1 GiB, and the UDF
  names), or mounted by Windows at **Play**. Encrypted Redump ISOs stay out: they need disc keys the port does not ship.
- **Saves between regions:** a US save copied as `BCES01741-*` may or may not load; try it once and document.

## Risks and open questions

- The game's own handling of a disc plus an update under our runtime (Phase 1 answers it first; RPCS3 runs it).
- APP_VER: whether the game reads it, and from where; a wrong one could hide the update's text.
- Greek: how it is chosen.
- The KLIC rule on other versions: the wide search and the RPCS3 log back it up.
- RPCS3's `--decrypt` stdin behaviour across versions: tested on 0.0.43; the launcher checks the output's hash anyway.
- A player with only an ISO: until Phase 8, a clear message and the extraction steps.

## Order and size

| phase | days | needs |
|---|---|---|
| 1 the game in a hand-made layout | 1 | the user's EU copy |
| 2 the title table | 1 | phase 1 |
| 3 finding an EU install | 1 to 1.5 | phase 2 |
| 4 decrypting without keys | 1 | phase 2 |
| 5 the rest that knew one title | 1 | phases 3 and 4 |
| 6 tests | 0.5 to 1 | phases 3 to 5 |
| 7 documents and release | 0.5 | phase 6 |
| 8 later | each on its own | copies or players |
