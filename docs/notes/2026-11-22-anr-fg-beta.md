# ANR FG as a beta choice of frame generation (2026-11-22)

The experiment of 2026-11-12 (branch `exp/anr-fg`, tried on a GTX 1650 Ti with ANR FG V.B14) is in the main line now, as
the third choice of **Frame generation** in the launcher: Off, AMD FSR, **ANR FG (beta)** (`graphics.frame_generation =
anr`). [Apex Neural Rendering](https://github.com/apex-compute/ANR)'s frame generation makes the frames between the
game's, while FSR's frame generation swap chain still presents and paces them.

## What ANR is to the port

- **Not part of it.** ANR FG is closed, in beta, and comes with no licence. Nothing of it is in the repository or the
  download, and the program never fetches it: the player downloads a release's zip (`anr-fg-V.B20-full.zip` or the
  addon zip) and the launcher's ready check takes it (**Add zip**), or `Ascension-R.exe --anr-zip <zip>`. That unpacks
  the folder that holds `nvngx_dlssg.dll` (`OptiScaler\custom\Apex Neural Rendering FG\dlssg` in the zip) into `anr\`
  beside the exe, `graphics.anr_dll`'s folder; the zip is unpacked as a mod's is (no name outside the folder, none
  Windows refuses).
- **Signed or not loaded.** Since FG V.B16 the DLL is signed by Apex Compute, Inc. (an EV certificate from GlobalSign).
  `rsx_anr_open` checks the signature with WinVerifyTrust, offline (no revocation lookup: a start must not wait on the
  network), and loads the DLL only when the signer is Apex Compute, Inc.; `D3D12_ANR_UNSIGNED=1` loads another for a
  test. The log names the signer, the size and the start of the SHA-256:
  `[anr] ...\anr\nvngx_dlssg.dll: signed by Apex Compute, Inc., 3684136 bytes, SHA-256 94dc4f10b20d8034...`.
- **Our own declarations of the interface.** The DLL is a DLSS-G provider: NGX's D3D12 entry points and a parameter
  map the host hands it. The experiment compiled against three of NVIDIA's NGX headers, downloaded at configure time,
  under the NVIDIA RTX SDK license, which no release could carry. `ps3recomp/libs/video/rsx_ngx.h` now declares what a
  host needs, written for interoperability: the calling convention, the result codes (failure = 0xBAD in the top 12
  bits), the API version 0x15, feature 11, the parameter map's virtual functions in the order the DLL calls them, and
  the 77 names it reads ("DLSSG.Backbuffer" and so on). The build downloads nothing for it. The exported function names
  are looked up by name.

## The calls

As in the experiment (`rsx_anr.cpp`): `NVSDK_NGX_D3D12_Init_Ext` (application 1, the temp folder, the device),
`PopulateParameters_Impl` (it offers up to 5 generated frames; we ask for 1), `CreateFeature(FrameGeneration)` at the
first generated frame, one `EvaluateFeature` a frame from FSR's swap chain callback (`fsr3_anr_generate`), which runs on
the presenting thread inside its Present, so the frame's depth, motion and picture without its HUD are still as the
frame left them. Depth goes to ANR as R32_FLOAT, as FSR has it (ANR's V.B18 fixed a 24-bit depth bug on AMD that this
path never met). A reset, a cut or a failed evaluation shows the real frame twice; when the feature cannot be made, or
ten evaluations fail in a row, FSR's own frame generation takes over from the next frame.

New since the experiment:

- **The swap chain kept at 3.1.** ANR's frames come from the 3.1 swap chain's callback, which has been read and tried.
  The FSR API would give an RX 9000 the 4.0 swap chain, whose Present has not been, so with ANR frame generation and its
  swap chain are pinned to 3.1 (`rsx_fsr3_fg_version("3.1")`, through `ffxQueryDescGetVersions` and `ffxOverrideVersion`
  as the upscaler's version): `[fsr3] swapchain: 3.1.7, as asked (3.1)`.
- **The launcher**: Frame generation is a list (Off, AMD FSR, ANR FG (beta)); the ready check's last line says
  `Upscaling: AMD FSR 4.1.2 + ANR FG`, or `ANR FG's files are not here yet` with **Add zip**; the footer says ANR FG; the
  freeze offer counts anr as on, ANR's frames going through the same swap chain. Problem reports have a line a session:
  `ANR FG: signed by Apex Compute, Inc., 3684136 bytes, SHA-256 ...; made frames at 1920x1080 from 1920x1080`, or why it
  was not loaded, failed or stood aside.
- **The stats panel** says `Upscaler: FSR 4.1.2 + FG ANR` while ANR makes the frames.
- **`D3D12_FG_ONLY_GENERATED=1`** has the swap chain show only the generated frames (FSR's `onlyPresentGenerated`), so
  that a screen capture takes nothing but generated frames: the way the two were compared below.

## Measured on an RX 6700 XT (FG V.B20)

1080p from 1080p, FSR 4.1.2 upscaling, frame generation at 120 Hz, the bench route's checkpoint (Profile 1) with the
character walking against a wall for the motion, an i5-12400F. ANR's own log (`nr_fg-*.log` in `anr\`) and the
census's GPU times:

- **ANR's path:** `GPU path table: rdna2 (amd), portable offered, order portable`: its portable program, on a Vulkan
  device of its own on the same GPU (`native bridge`), the game's textures mirrored in and the frame out.
- **Its cost:** about 2.6 ms of GPU time a real frame (medians: pair 1.2 to 1.3, the generated frame's phase 0.8 to 1.3,
  out 0.14, in 0.05; its Vulkan passes 2.4 to 2.9 ms a batch with the waits). Evaluate on our thread 0.33 to 0.48 ms at
  p99, the interop about 0.1 ms. 1800 generated frames a run, no generation error.
- **The frame rate:** the spot is held by the CPU (the PPU thread at 84 to 100%). Real frames in 5 s windows of play:
  FSR's frame generation 183 to 200 (about 38 a second), ANR's 177 to 195 (about 36.8 a second).
- **The frames:** with only the generated frames shown, grabbed twice a second over 18 s of walking: FSR's tear and
  double the character's arm and glove at the waist and smear her legs and boots; ANR's keep them whole. The same as
  the GTX 1650 Ti's runs of 2026-11-12.

A test harness note: a game started from a background shell is not let take the foreground, and a borderless window
behind the taskbar leaves the taskbar on top of it; the first A/B looked as if ANR brought the taskbar up. Watching the
foreground window showed the same with FSR's frame generation in that state, so the harness now brings the game's window
forward before it grabs the screen.

## Not tried

VRR, 144 Hz and over, input latency, resizing while ANR runs, NVIDIA and Intel GPUs with this build (the GTX 1650 Ti ran
the experiment), an RX 9000 with its 4.0 swap chain pinned back to 3.1.
