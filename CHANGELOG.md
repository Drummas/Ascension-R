## v0.5.0

**Ascension-R 0.5.0** is the version that can be moved: an installed folder keeps everything it uses inside itself.

- **Installation:** every path in `ascension-r.ini` is kept relative to the folder the settings live in (now beside
  `Ascension-R.exe`), so an installed folder can be moved or copied whole, to another drive or another PC, and
  nothing is written outside it. A copy whose settings are still in `%LOCALAPPDATA%\Ascension-R` is offered its files
  on the first start, and their paths are made relative with them.
- **Releases:** the Release workflow compiles `Ascension-R.exe` and packages the Kit with no game files on the
  machine that makes it, since the launcher holds none of the game's code, and the release page appears only once
  its files are on it.

## v0.4.1

**Ascension-R 0.4.1** is the version the launcher's Clean look, the graphics options added since 0.2.0 and the
multiplayer work come together in.

- **Picture:** field of view in play, ambient occlusion, shadow and effects resolution, debanding, CAS sharpening,
  contrast and vibrance, and HDR with its peak brightness and paper white.
- **NVIDIA Reflex** and **NVIDIA DLSS frame generation** in beta, with Streamline's DLLs beside the program; frame
  generation can be switched off again when a card's driver stops with it.
- **VRAM:** the pool is watched through each level's load, with a reserve for them (#39, #42), and a texture unit
  that was turned off but still bound no longer draws the red cell door wrong (issue #34).
- **Ultrawide:** copies of the display are no longer squeezed into the 16:9 (issue #48).
- **Launcher:** Clean window style by default, an Ultra preset in place of Faithful, Smooth and Balanced as full
  steps, and Indonesian, Chinese, Russian, Spanish, Portuguese and German.
- **Textures and mods:** DDS pictures, a texture pack's upscaling (`modtools upscale`), and `modtools extract` for
  every texture of the game's files.
- **Runtime:** a SPURS policy module that runs on for seconds is logged with the SPU's events, interrupts, parked
  lists and reservation (#50).
- **Fixed:** the black squares and triangles on the floor under Megaera were a shadow map ending at its corner.
