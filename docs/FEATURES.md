# Features and settings

Settings live in `ascension-r.ini`, and the launcher edits them. Its folder, which also takes the logs, the saves and the shader
caches, is `%LOCALAPPDATA%\Ascension-R`. A copy with a file called `portable.txt` beside the exe keeps them all there instead, as a
build from source does.

## Game folder, shaders, logs and recordings

The launcher finds the game's folder and decrypts `GOWA.SELF` by itself, with RPCS3 and the game's license file (`.rap`). It looks for
both beside the game when the game is installed in RPCS3, and otherwise asks. It can download the official RPCS3 build for this, once, if
you say so, and it removes it again. It works on copies in the folder of the settings and writes nothing to the game's folder or to an
RPCS3 of yours. `Ascension-R --prepare-game <folder> [--rpcs3 <rpcs3.exe>] [--rap <file>]` does the same without the window.

The launcher shows the game's folder in its System tab. Browse picks another one, and Auto detect looks for the game
on every disk; it starts by itself when the game is not where the settings say.

At most every six hours the launcher asks GitHub for the repository's releases (`api.github.com`, saying only
`Ascension-R/<version>` as its User-Agent) and says when one newer than itself is out, pre-releases too: a notice on the
Play tab whose Download opens the release's page, and the number in gold under its own in the sidebar, which opens it
too. Closing the notice hides it for that release; the sidebar's line stays until the update. What the last answer said
is kept in `update_check.txt` beside the settings file, so the notice shows at once at the next start and the settings
file is not written. Check for updates, in the System tab (`launcher.update_check`), turns it off; a PC with no network
sees nothing. `GOWA_UPDATE_FEED=<file>` reads the list from a file instead, to try it
([note](notes/2026-11-13-update-check.md)).

Before it decrypts or builds anything, the launcher checks that the folder holds the whole game: USRDIR's 48 archives
and the two lists that name them, each by its size and the SHA-256 of its first and last 64 KiB, as version 1.12 has
them (`port/game_files.inc`, made by `gowa.py game-files`). A folder that lacks some, or has one of another size or
content, is not taken, whatever was decrypted from it before: the System tab says how many files are missing and which
first, and Build and Play wait. A game started without the launcher that cannot open one of them says which and stops,
rather than stop a few seconds in with a black window ([note](notes/2026-11-10-game-files-check.md)).

`build` copies `dxcompiler.dll` and `dxil.dll` from the Windows SDK next to the exe, and guest shaders compile with
them. Without the two files they compile with D3DCompile, about 2.4 times slower. `graphics.shader_compiler = fxc`
asks for that too. The two compilers keep their caches apart, so a first run on either compiles everything once.
Each cache keeps every program once and is packed with zstd: 2,287 programs and 2,309 pipelines take 5.9 MB, where
the files before took 83 MB. A cache from an older build is converted at the first start, on a thread of its own.
The pipelines kept in it are built on several threads at the start, and the title waits for them, a third of a second
here: no pipeline the cache has is then built in play. `graphics.pipeline_wait = off` (Build pipelines first, in the
Graphics tab) lets the game go on while they build.
Before its first start of each version the game reads its archives and compiles every vertex shader in them into the
cache, and does not start before it is done: an 8-bit screen where its window is about to open shows how far it is
(`port/loading_screen.cpp`, `port/precompile.cpp`). The first time that is 3,455 programs, a minute or two, 3 MB more
on disk; the programs it finds are kept beside the cache, so after an update it takes seconds. A session of the first
level then compiled 4 vertex shaders where it had compiled 212. Clear shaders makes the next start do it again.
`GOWA_PRECOMPILE_FIRST=0` leaves it out (the benches do).
Pixel shaders (`graphics.shader_prebuild`, Pixel shaders built ahead, on by default; DXC only): each fragment program's
text reads what its draw binds and sets as it runs, so it can be built before a draw needs it
([note](notes/2026-11-18-fp-text-without-state.md)). The precompile's screen builds them after the vertex shaders, on
the first start of each version (Enter or a controller's Start leaves the rest for the next start), and **Build all
shaders now**, down the launcher's sidebar or as Build in the Play tab's ready check, does the same from the launcher:
those of the archives into `<cache>.dxil.prebuilt` (49,996 programs, 39,598
pixel shaders, 309 MB; some 7 minutes on six cores), and the game takes them from there: on the fight replay from an
empty cache 282 of its 283 pixel shaders came from it. The alpha test is read as each program runs, so the
alpha-tested draws share the same programs ([note](notes/2026-11-18-pixel-shader-prebuild-alpha-test.md)). It never runs beside the game,
which cost 7% of the frames ([note](notes/2026-11-18-pixel-shader-prebuild-step2.md)). With it on, the pipelines and
pixel shaders of the old texts leave the cache at the next pack and are not built at the start
([note](notes/2026-11-18-pixel-shader-prebuild-step3.md)).
The screen has music of its own: an original theme over the sea, the brazier and thunder after the scene's lightning,
made by the program as the screen opens (`port/precompile_music.cpp`, [note](notes/2026-11-13-precompile-music.md)).
Precompile music, in the System tab, sets it to Off, Low, Normal (the default) or High.
Clear shaders, in the launcher's sidebar, moves both to the Recycle Bin.

Each session started from the launcher (not from a script) writes its output to `logs\session-<date>-<time>.log` beside
the settings file; the five newest are kept, and the console window gives the path. How the session ended is at its
end: `[rsx] window closed`, `sys_process_exit` from the game, or `[crash]` with the exception, its address and the
crashed thread's stack (offsets in `Ascension-R.exe` read against `Ascension-R.map`).

Beside each log, `session-<date>-<time>.pad` records what the game read from the pad, with the files it opened and the
threads it started. `gowa.py bench --replay <file>` plays one back, on a copy of the saves it started from
(`--set paths.hdd0=<copy>`), and takes the usual screenshots: a scene reached in play is reached again with no hand on
the pad. The playback waits at each file the recording saw opened until this run has opened it too, so a load that
takes longer does not throw it off. A recorded run through the menus to Profile 3, played back, gave the same frames
20 to 100 s after the load.

`logs\missed_code.txt` keeps, over the sessions, the code that ran without a lift of it: SPU code in the interpreter and
PPU calls that found no lifted function. `gowa.py missed` shows it, and the next `gowa.py lift` takes it into
`scripts/spu_pic_pieces.json` and `scripts/jobmods_extra.json` first (`--no-missed`: not). `PS3_MISSED_CODE=<file>`
records in any run, and `=0` not at all.

The GPU's work is recorded, submitted and presented on a thread of its own, `rsx render`, beside the one that walks
the game's command buffer. Where that walk was the limit it gives about 10% (the gate with shadows on, 30 to 33 frames
a second). `graphics.render_thread = off` (Render thread in the launcher's Graphics tab) puts both back on one thread.

## Optimise for this PC

With Optimise for this PC on (System tab, `launcher.optimise`, off at first), the Kit's build of the game's code makes a
training copy first: instrumented, it plays the game's opening by itself for about seven minutes, in a window of its
own, muted, deaf to the player's controllers and keyboard, on an hdd0 of its own (the game's folder through a junction,
only read) with a copy of the shader cache. The build then optimizes with what it counted (clang's profile-guided
optimization): 2-3% more frames in Sparta's fight on the test laptop, for about 15 minutes more a build and 3 GB of free
disk space while it runs. A training that does not get through is made once more, then the build goes on without it;
`game-code\ascension_game.ini` says `pgo = on (...)`, `none (why)` or `off`. Turned on after a build, Play builds the
game's code again with it ([note](notes/2026-11-14-kit-pgo.md)).

## Which graphics card

On a PC with two GPUs, Graphics card in the launcher's Graphics tab (`graphics.gpu`: `discrete`, the default, or `integrated`)
says which one the game runs on, by the names Windows gives them. The row is not shown on a PC with one GPU.

## Internal resolution

Internal resolution in the launcher's Graphics tab (`graphics.render_scale`) draws the scene above 720p: a number from 1
to 4, or `native` for the window's size. Targets the size of the display are drawn larger. Bloom, blur and shadow maps
stay at the game's size, and what the game reads back is brought down to it. AMD FSR and frame generation go no higher
than the window, and the log says so. Otherwise a render larger than the window is scaled down to it. The first session
at a new scale compiles part of the shaders again. Disable Mesh Trimming in Game patches is meant for this, though on the
route it made no visible difference at 2x. The [note](notes/2026-11-08-internal-resolution.md) has what was measured
and what has not been tried.

## Ultrawide

Ultrawide in the launcher's Display tab (`display.ultrawide`, off by default) draws the game to the full width of a screen
wider than 16:9. The vertical view stays as it was and more shows at the sides. The HUD, menus and movies stay 16:9 in the
middle, with black bars beside a movie or a menu that has no game behind it. Any width works, 21:9 and 32:9 among them. In
a window it goes by `display.window_size`, and otherwise by the monitor the game is on: the game opens on the monitor the
launcher was on when Play was pressed, so an ultrawide monitor beside a 16:9 main one works too. It takes effect at the
next start, and the first session compiles part of the shaders again.
Frame generation works without its pass for moving objects at these widths. The
[note](notes/2026-11-10-ultrawide.md) has what was measured and what has not been tried.

## Frame rate cap

Frame rate cap in the launcher's Display tab (`display.frame_cap`). Off, the default, is the game's own pace: 60 frames a
second at most, as on a PS3. 20 and 30 give an even pace for a PC that cannot hold more: with VSync on, every frame
stays on screen for the same number of refreshes.

120, 144 and Unlocked are experimental and let the game run past 60 at its own speed. A patch of the title
(`unlock_fps`) has each frame move the world by its own length, where the game moved it at least a 60th of a second,
and the frame clock lets a frame come up to the cap's pace (Unlocked: as fast as the PC goes). With VSync on, the
monitor's refresh rate is the most, and the swap chain has three buffers, so a game that cannot hold the refresh shows
what it makes instead of dropping to half of it (Village of Kirra on a 120 Hz display: 66-113 instead of 51-60).
Frame generation is off with these, and the game goes back to 60 when it goes online
for multiplayer, until it is started again. On an i5-12400F with an RX 6700 XT, VSync off: the title, the menus and the
opening movie at 120, the first fight held by the CPU at 37-53 as without the patch; every frame's step equal to its
real length, the movie's clock at 1.000 s a second, and the first level's load 1-3 s shorter than at 60, as the game
loads a little each frame. A 144 Hz monitor and the game past the first level have not been tried
([note](notes/2026-11-23-unlock-fps.md)).

While a level loads the frame rate is held to 60, and textures count as unused after 4 s at any frame rate: unlocked,
a tester's game ran out of video memory as levels loaded (at the start of the game and at the Megaera cinematic) and
stopped, which it never did with the cap off ([note](notes/2026-11-24-unlock-fps-pool.md), issue #39). The same
happened at 60 frames a second at 32:9 (#42): the streamed textures now leave 16 MB of the game's video memory to the
levels' loads, at any frame rate.

## Frame rate on screen

Frame rate display in the launcher's Display tab (`display.show_fps`): in the title bar (the default), off, or on screen,
a panel in the top right corner, in an 8-bit look with no glow. The panel shows the frame rate and the frame time, the
load of the CPU, the GPU and the guest's processors (PPU, SPU, RSX) with a meter each, and a graph of the last frames,
two to a bar, the slower of each pair: cyan near the usual frame time, amber from 1.25 times it, red from 1.8 times, a
hitch. The frame rate turns amber under 29 and red under 20, as the game holds 30. It names no hardware. `show_fps =
stats` in `ascension-r.ini` shows the larger stats panel instead, for diagnosis: the loads, memory, the graphics card's
and CPU's names, and Kratos's position.

## Colour vibrance and contrast

Two rows in the launcher's Graphics tab (#26), Off to Max, both off by default: the game's own muted, golden look stays
the default. They grade the picture at the end of the presentation pass, after the scaling and before the port's
overlay, so the game's HUD and menus are graded with it and the frame rate panel is not.

- **Colour vibrance** (`graphics.vibrance`) moves each colour away from its grey by 1 + V x (1 - its saturation): dull
  colours the most, strong ones (and skin) little. V is 0.2, 0.4, 0.6 and 0.9 from Low to Max.
- **Contrast** (`graphics.contrast`) puts the luminance on an S-curve (smoothstep, by 0.15, 0.3, 0.45 and 0.65) and
  scales the colour with it: darks a little darker, lights a little lighter, black and white kept.

Bilinear, sharp bilinear and FSR 1 do it in their last shader; AMD FSR does it on the upscaler's output, before the HUD
goes on, which keeps frame generation's picture without the HUD like the frame. It costs next to nothing. On the
loading screen's logo, High vibrance with Medium contrast took the mean saturation from 0.74 to 0.86 and left the black
at 0. Screenshots with `display.screenshot = game` keep the game's own frame, ungraded.

## AMD FSR

Two rows in the launcher's Graphics tab, both off by default, measured on a GTX 1650 Ti, and the version of the first.
`build` copies their DLLs from an [FSR SDK 2.4.0](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK) unpacked
under `../fsr-sdk`, or from local.json's `fsr_dir`. Without the DLLs the log says so and the game goes on without FSR.

- **Scaling: AMD FSR** (`graphics.scaling = fsr3`) rebuilds scene frames from 720p with jitter, depth and motion, in
  place of SMAA. Logos, menus and loading screens keep FSR 1. On a GTX 1650 Ti it takes 2.0 ms at 1600x900, where FSR 1 and
  SMAA take 1.1. The HUD stays at 720p sharpness.
- **FSR version** (`graphics.fsr_version`): `auto`, the default, lets the FSR API take the newest upscaler the GPU and
  its driver have. With SDK 2.4.0's DLLs that is FSR 4.1.2, a machine-learned model, on AMD Radeon RX 6000 and newer
  (the RX 6000 needs driver 26.10.1 or later), and FSR 3.1.6 on other GPUs. `3.1` pins 3.1.6. The log lists what the GPU
  has and says which one runs (`[fsr3] upscaler versions on this GPU: 4.1.2, 3.1.6, 2.3.4`, `[fsr3] upscaler: 4.1.2`);
  the launcher's ready check, the stats panel and problem reports show it too. On an RX 6700 XT at 1080p from 1080p,
  4.1.2 costs about 1.2 ms of GPU time a frame more than 3.1.6 and gives cleaner edges and thin lines, where 3.1.6 keeps
  textures a little sharper; in a spot where the CPU sets the pace the frame rate was the same
  ([note](notes/2026-11-22-fsr-versions.md)).
- **Frame generation** (`graphics.frame_generation = on`) shows two frames for each of the game's, so keep VSync on. It
  holds the game at half the monitor's refresh rate: 30 frames a second at 60 Hz, 60 at 120 Hz. Past 120 Hz it halves that
  again, as 60 is the most a PS3 flips and a frame should stay on screen for a whole number of refreshes: 36 at 144 Hz, 60
  at 240 Hz. Only 60 Hz has been tried on a real display, and the game has not been played above 39 frames a second.
  With VSync on, up to 120 Hz, that pace comes from VSync itself, which keeps the game up to about 15 ms ahead of the
  display and takes up what a slow frame loses. A Frame rate cap comes first: it gives those milliseconds back for a less
  even pace, and suits a PC that cannot hold the rate, 30 on a 120 Hz monitor.
  `graphics.frame_generation_refresh` gives the rate by hand, for a VRR display: 120 on a 144 Hz one is 60 frames a second.
  While the game is under 25 generation stands aside (`graphics.frame_generation_floor`).
  On one hybrid laptop, frame generation froze the game at its boot logos about every other start, its GPU stopped in a
  present, whenever the session before had ended itself. The game is now ended by a second copy of the exe when its
  window closes, and the freeze did not come back in 14 starts ([note](notes/2026-11-11-fg-freeze-exit.md)). When a
  session still freezes with it on, the launcher's next start asks whether to turn it off.
- **ANR FG (beta)** (`graphics.frame_generation = anr`): [Apex Neural Rendering](https://github.com/apex-compute/ANR)'s
  frame generation makes the frames in between, while FSR's swap chain presents and paces them as above. ANR is closed
  and has no licence: nothing of it ships. Chosen without its files, the launcher asks, and with the player's yes
  downloads the newest release's addon zip from Apex Compute's GitHub releases, checks its SHA-256 and the DLL's
  signature and unpacks it into `anr\` beside the exe; **Choose a zip I have** takes the player's own (`--anr-get` and
  `--anr-zip <zip>` from a command line; not ANR's own installer, which would put OptiScaler there). The DLL is loaded
  only when Apex Compute, Inc. signed it.
  The port talks to it through the DLSS-G interface, declared in `rsx_ngx.h` without NVIDIA's SDK. With it, frame
  generation and its swap chain stay at 3.1; when it cannot start, FSR's own frame generation takes over. On an RX 6700
  XT at 1080p (FG V.B20, its portable path) it took about 2.6 ms of GPU time a real frame and generated 1800 frames a run
  without an error, and where FSR's generated frames tore and doubled a walking character's arms and legs, its kept them
  whole ([note](notes/2026-11-22-anr-fg-beta.md)).

Both take what moves from the title's motion blur draws, so Disable Motion Blur is left off with them: EDGE goes from 46
to 67 ms a flip, and a fight at the 30 cap loses about 0.3 frames a second on a cool machine, more on a hot one.
`graphics.frame_generation_objects = off` goes back to the camera's motion alone, and the patch applies. Both take the
title's frame order without MLAA, which the game switches on for them (`mlaa_path_off`): with MLAA the depth at the final
composite is the next frame's. In that order the bloom and the motion blur are drawn and then written over, so with AMD
FSR or frame generation there is no bloom. The [plan](notes/2026-11-07-fsr31-plan.md) has the measurements.

Disable MLAA in the Patches tab (on by default) has the PS3's SPU anti-aliasing, whose picture this port never shows, do
no work, as RPCS3's Disable SPU MLAA does: the title keeps its frame order with MLAA, so the bloom reaches the picture,
at the frame rate of the order without it ([note](notes/2026-11-23-bloom-spu-mlaa.md)).

## NVIDIA DLSS (beta)

**Scaling: NVIDIA DLSS (RTX cards)** (`graphics.scaling = dlss`) has DLSS Super Resolution rebuild scene frames in AMD
FSR's place, from the same jitter, depth and motion, on GeForce RTX and other NVIDIA RTX cards. Not yet tried on one: the
[note](notes/2026-11-23-dlss.md) has what was checked here and what a tester looks at.

- The build fetches NVIDIA's NGX SDK (DLSS SDK 310.9.16) into the build folder; nothing of NVIDIA's is in this repository
  or the download. Picked without the DLL, the launcher asks, and with the player's yes downloads `nvngx_dlss.dll`
  310.9.16 (59 MB) from NVIDIA's own DLSS repository on GitHub, checks its size, SHA-256 and NVIDIA's signature, and puts
  it in `dlss\` beside the exe (`--dlss-get` from a command line).
- The mode follows the Internal resolution against the window: of DLAA, Quality, Balanced, Performance and Ultra
  Performance, the one whose range of render sizes takes the game's and whose own scale is nearest: 1080p internal in a
  1080p window is DLAA, and in a 1440p or 4K one should be Quality or Performance (the log lists each mode's range). **DLSS preset** (`graphics.dlss_preset`): `auto` leaves
  each mode the DLL's own (K for DLAA, Quality and Balanced, M for Performance, L for Ultra Performance); `k`, `l`, `m` or `j` asks
  every mode for that one.
- Where it cannot run the game uses AMD FSR and the log says why: not an NVIDIA card, no NGX in the driver, a driver too
  old for DLSS, no DLL, no mode for the sizes, or three failed frames in a row. MLAA's frame order goes as with FSR
  (`mlaa_path_off`), and FSR sharpening does not apply. The stats panel shows `DLSS 310.9.16 Quality`.
- The log has each mode's sizes (`[dlss]`), and NGX's own lines (`[ngx]`) with `D3D12_DLSS_LOG=on`. The first RTX
  reports and what came of them: [note](notes/2026-11-24-dlss-test1.md); since then the upscaler's jitter stays off
  the HUD and off menus, with AMD FSR too. `D3D12_DLSS_JITTER=x,y` and `D3D12_DLSS_MV=x,y`
  multiply what DLSS is told of the jitter and the motion (`-1` turns one round), for a tester to try where the picture
  shakes or smears.

## Controllers

XInput reads Xbox controllers and the PC pads that work like them, as before. With `SDL3.dll` beside the exe, SDL 3
reads the others: the DualShock 4, the DualSense, Switch controllers and the DirectInput pads SDL knows. Each goes
through the same dead zone and stick handling. Controller API in the launcher's Controls tab (`input.api`) chooses:
Auto, the default, takes each controller through XInput when it has it and through SDL3 when not; XInput leaves SDL3
out; SDL3 reads every controller, Xbox ones too. The Play tab's ready check names the controller and what reads it. A
DualShock 3 needs a driver such as DsHidMini, and with DS4Windows XInput is the setting, or the pad counts twice
([note](notes/2026-11-10-controllers.md)).

**Xbox button icons** are an optional mod that comes in the download (`optional mods\Xbox button icons`; in the tree
`optional-mods/`): the game shows its own PlayStation buttons until a player copies the mod into the mods folder.
Then A, B, X and Y stand where Cross, Circle, Square and Triangle are, and View for Select: Ascension-R's own
pictures, drawn by `scripts/button_icons.ps1`, in place of the game's button textures as a texture mod's are (below)
([note](notes/2026-11-18-mods-textures.md)).

## Sound

The game's sound goes to Windows through WASAPI in shared mode, so the effects of Windows and of the sound card apply to
it as to any program: Equalizer APO and other equalizers, Loudness Equalization, virtual surround, and the Dolby, DTS or
Nahimic suites. The stream says it is a game's, which some of those suites use to pick their game profile.

- **Steady audio** (System, on): the game's sound runs on a worker of its own, so heavy fights do not break it up.
- **Speakers** (`system.speakers`, Auto): the game mixes up to 7.1. Auto sends 7.1 to a 7.1 device, 5.1 to a 5.1 one
  and stereo to the rest, as Windows has each set up. Set 7.1 or 5.1 by hand for Windows Sonic or Dolby Atmos for
  Headphones, which make surround for headphones out of it. On a plain stereo device Windows folds it down. The game is
  told what the output takes, but it fills the surround channels only with its own Sound Mode (Options, Audio) on 5.1
  or 7.1 Surround.
- **Bypass sound effects** (`system.raw_audio`, off): the stream skips those effects, where the driver has a way past
  them. The log says whether it did.
- **A change of output device**, such as headphones plugged in, a Bluetooth headset or another default device in
  Windows, moves the sound to the new default device within a second. Before, the sound stopped until the next start.

The [note](notes/2026-11-11-audio-output.md) has the details.

## Cheats

The launcher's Cheats tab: Damage to Kratos (half, a quarter or none), Kratos's damage (2x, 5x or one hit), Max red orbs,
Infinite magic and items, Infinite rage and Infinite double jumps. All are off by default and hook the title's own code, its
damage, its meters and its jump ([note](notes/2026-11-07-cheats.md)).

## Mods

The `mods` folder beside the settings file (`build\mods\` in a build tree; `[mods] folder` names another) holds a folder
or a `.zip` for each mod. The launcher's **Mods** tab lists them in their order, each with its switch, up and down, and
what it gives: its files, how many of them a mod above it has too (the first one in the list wins), and what this build
does not read. **Use mods** (`mods.use`, on) leaves them all out when off. The game takes the files of the mods that are
on, whichever USRDIR it reads them from (a disc's or its update's), in place of the game's or added where the game has
none; the game's own folder is never changed. A `.zip` is unpacked once into `mods\.unpacked\`, and again when it
changes. A mod's `archive\` (files for entries of the game's archives, by their names there) and `text\` (lines of the
game's text, as `gowa.py text export` writes them) go into one more update of the game, which the game makes as it
starts, with the Kit's Python, and again only when they change: an entry the game's updates patch goes in as a `.PATCH`
of one step, a line that fails the text checks is left out, and the first mod in the list wins
([note](notes/2026-11-18-mods-archive-and-text.md)). A mod can bring only what it changes of a big file: a `.PATCH` in
the game's own form, made by `scripts/modtools.py patch`, with a `.PATCH.base` naming the game's file it is for, which
the packer checks first ([note](notes/2026-11-20-mods-aliases-and-patches.md)). A mod's `textures\` has PNGs named by
the id of a texture of the game's: each goes in that texture's place as the texture reaches the graphics card, at any
size, or over it as an overlay; its `aliases.txt` gives one picture to more textures; **Write out the game's
textures** (`mods.dump_textures`) writes each texture the game loads into `textures-dump\`, named by its id
([note](notes/2026-11-18-mods-textures.md)). The log has a `[mods]` line with each mod and what it gave, and
names each file taken (`[fs] mod`); the problem report has the same line, without paths. [MODDING.md](MODDING.md) has
the layout a mod comes in, its `mod.ini`, and how the settings keep the order (`[mods] order` and `off`).

`paths.mods` still names one older folder laid out like the PS3's paths, `dev_hdd0\game\NPUA80918\USRDIR\...`, read after
the mods folder. Empty, the default, means none.

The game's text, subtitles included, is plain UTF-8 inside its archives, so a translation can go in as a seventh update:
`TPPS6.PSARC` with the text patches, and `PATCHES` holding `6` ([note](notes/2026-11-11-game-text.md)). From a build tree,
`gowa.py text export [--part story]` writes the English text into `build\text\`, a line for each line of text, and
`gowa.py text build <translation files>` checks a translation and writes it as a mod, `build\mods\translation\`
(`--name` for another), which the Mods tab then lists. The game's folder is only read.

## Multiplayer (beta)

The launcher's **Multiplayer** tab (`[online]`) brings back the game's online modes with no PSN account; nothing is
sent to Sony's servers. Set an **Online ID** (`name`: 3 to 16 letters, digits, `-` and `_`, starting with a letter;
every player needs their own), choose how to meet (`mode`), then Multi-Player on the game's title screen and Quick
Play.

- **Auto** (`auto`): from the moment Auto is chosen, the launcher runs a node that finds the other Ascension-R players
  by itself, as torrent clients find their peers: on the BitTorrent DHT and on the local network. Nobody runs a server.
  The tab lists the players online and what each is doing, and the Play tab shows how many.
- **Host** (`host`) and **Join** (`join`): one PC runs the matchmaking for its own game and the players who join it at
  its address (**Host's address**, `server`): on one network, over the internet with the ports the tab names forwarded
  (TCP 10070 and 10012, TCP and UDP 36101), or on a virtual LAN.
- **Always relayed** (`relay`): the game's traffic goes by the host's PC or the players' nodes instead of straight to
  the other players, for a network where joining works and playing does not.
- **Open the port on the router** (`upnp`, on): Auto asks the router (UPnP) to forward the node's UDP port, 36102, so
  that other players reach this PC.
- **Help others connect** (`relay_others`, on): two players who cannot reach each other may talk through this PC, a few
  pairs at most.
- **Community nodes** (`nodes`): nodes anyone can run on a reachable machine, which introduce players and carry for
  them: `address:port`, a comma between. One runs with `kit\python\python.exe kit\scripts\mp_p2p.py community` in the
  download's folder, or `python3 scripts/mp_p2p.py community` from the repository, its UDP port 36102 reachable.

The launcher's cheats go off once the game goes online for multiplayer, until it is started again.

The website shows about how many players are online on Auto: every 20 minutes a GitHub Actions job
(`.github/workflows/online-status.yml`) looks them up on the DHT as a node does (`scripts/mp_status.py`), and puts
the count alone, with its time, as `status.json` on the `status` branch. It is a rough count: players behind a router
that maps by destination do not announce themselves, one who has just gone can still be counted for up to about 30
minutes, and Host and Join games are not on the DHT ([note](notes/2026-11-23-online-status.md)). How it works: the
notes from [phase 0](notes/2026-11-22-multiplayer-phase0.md) to [phase 7](notes/2026-11-22-multiplayer-phase7.md).
