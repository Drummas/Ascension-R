# NVIDIA Reflex through Streamline, step 2a of DLSS frame generation (2026-11-24)

DLSS Frame Generation needs NVIDIA Reflex, and Reflex on its own lowers input lag on any GeForce GTX 900 or newer. This
step brings in NVIDIA Streamline 2.14.16 with Reflex and PCL (PC latency stats) only; DLSS-G comes next on top of it.

## How it is put in

- `graphics.reflex` = off (the default), on or boost; the launcher's NVIDIA Reflex row, shown with an NVIDIA GPU.
- ps3recomp's `libs/video/rsx_sl.cpp` loads `sl.interposer.dll` from beside the exe once WinVerifyTrust finds it signed
  by NVIDIA Corporation, with manual hooking, no updates over the network and the Reflex and PCL plugins alone. Its
  functions come from GetProcAddress and slGetFeatureFunction: nothing links against Streamline. Headers: ps3recomp's
  `third_party/streamline` (MIT).
- It starts after the device and before the swap chain, which is made through Streamline's factory so Streamline's
  present runs each frame (manual hooking asks for that; without it Streamline's per-frame state grows). A swap chain
  that is not Streamline's turns it off again. Not with frame generation: FSR makes its own swap chain from ours.
- Where a frame starts: the title builds frame N+1 once flip N completes, so the Reflex sleep for N+1 goes just before
  `cellGcmTickFlip` completes a flip the title waits on (`g_gcm_flip_release_hook`), and N+1's simulation start just
  after. Its simulation ends when the drain reaches the title's next flip (the flip observer); frame N's render
  submission and present are marked around the backend's present of it. PCL's latency ping, a thread message, is taken
  in both message pumps.
- Releases carry `sl.interposer`, `sl.common`, `sl.reflex` and `sl.pcl.dll` from the SDK zip's `bin/x64`, NVIDIA's
  signed ones, each checked by its SHA-256 in `gowa.py`, with the MIT text as `licenses\NVIDIA-Streamline.txt`.

## Checked on this PC (RX 6700 XT, no Reflex)

`D3D12_REFLEX_ANY_GPU=1` loads Streamline on any GPU; Reflex's low latency is then not available and the markers feed
the latency stats alone (Streamline: "collecting latency stats only").

- Bench to the Megaera fight, one run a side (and the retry each got from the level check, which counts 30 fps or more
  as a menu here): reflex off 54.93 / 56.67 flips/s, Streamline on 54.93 / 56.08. No difference to tell.
- Streamline's verbose log (`D3D12_SL_VERBOSE=1`): the factory upgraded to its proxy, sl.common's Present and
  ResizeBuffers hooks in place, the three plugins loaded from beside the exe, no OTA.
- Memory at the title, sampled every 5 s: 5039-5044 MB from 45 s to 100 s, ~3,000 presents. Nothing grows.
- Reflex off and not an NVIDIA GPU: Streamline is not loaded at all.

## To check on an NVIDIA GPU

On the test laptop (GTX 1650 Ti, Optimus: the game must run on the GeForce):

- The log's `[D3D12] reflex: on (... low latency available ...)`; the stats panel's last line `Reflex On`.
- Frame rate with Reflex Off, On and On + Boost, VSync off, the same place: On should cost nothing where the CPU sets
  the pace and lower the latency where the GPU does (a higher internal resolution).
- NVIDIA's overlay (Alt+R in the NVIDIA app) shows PC latency once PCL's markers come through.
- DLSS with Reflex on: Streamline and the port's own NGX side by side.

## Step 2b: DLSS Frame Generation (2x)

- `graphics.frame_generation = dlss`: the launcher's NVIDIA DLSS (beta, RTX 40 and newer). Streamline starts with the
  DLSS-G plugin as well (`sl.dlss_g.dll`, shipped with the others), and Reflex on with it whatever `graphics.reflex`
  says. Where `slIsFeatureSupported` says no (not RTX 40+, driver, hardware-accelerated GPU scheduling off) the plugin is
  unloaded again before the swap chain is made, and the game runs without frame generation.
- DLSS-G's model, `nvngx_dlssg.dll` 310.9.16, is NVIDIA's under the RTX SDKs license and not shipped: the launcher offers
  to fetch it from NVIDIA/DLSS at the commit of v310.9.16 (the same file the Streamline 2.14.16 zip carries: git blob
  71b8070c, SHA-256 8d59d49b), checks its size, SHA-256 and NVIDIA's signature and puts it in `dlss\`, which is given to
  Streamline as a second folder to look in.
- Its inputs are FSR frame generation's: the depth and motion targets of FSR's inputs' pass (R32_FLOAT 0 near, R16G16_FLOAT
  in UV units, camera and objects; `rsx_fsr3_prepare_once`), the picture without its HUD at the back buffer's size, all
  tagged until the present. Its constants come from the title's world-to-clip matrix (`rsx_fsr3_pose_get`): the
  clip-to-previous-clip pair from this frame's and the last one's, the projection from near, far and the field of view,
  the camera's position and axes. All under the frame index its present markers carry.
- On for a 3D scene, off (inputs untagged) for menus, logos and movies; off before a swap chain resize. Its state is
  read after 120 frames and every 600: a failure turns it off for good, its reason logged.
- The pace as with FSR's: the game held at half the display's refresh.

Checked here (RX 6700 XT) with `D3D12_REFLEX_ANY_GPU=1 D3D12_DLSSG_DRYRUN=1`, which gives Streamline the inputs and
constants each frame with nothing generated: Streamline took 120 frames of them without a warning; the plugin itself
said "not supported on current hardware", as it should. Without the switches, an AMD GPU: Streamline not loaded, frame
generation off, the game as before. Nothing on an RTX 40 or 50 yet.

## 2026-11-25: on an RTX 5060, then turned off

A tester in #39 (RTX 5060, Ryzen 5 5600X, 1080p at 144 Hz, VSync on, cap Off) ran the test build `dlss-test-3` with
DLSS scaling and DLSS frame generation (`report-20261124-145426`), and with FSR scaling and AMD FSR's frame
generation (`report-20261124-150319`). The log of the first:

- The Streamline DLLs verified as signed by NVIDIA, `DLSS frame generation: loaded`, Reflex on by itself (low latency
  available, PC latency stats on), `running, 2 frames shown per frame, up to 5 generated, VSync with it supported`;
  no state check failed.
- The game held at 36 flips a second (144 Hz / 4), so 72 on screen.
- Off and on again at each movie and load, with short runs on at the edges of them (6 frames at 913-919, 20 at
  2706-2726): NVIDIA's frame generation indicator came and went with them. The log names the first 6 changes only.
- Two Streamline warnings, both harmless: the back buffer's extent not given (it takes the whole 1920x1080), and a
  clone's alignment overridden.

The tester's word: DLSS frame generation is far cleaner than AMD FSR's (no broken UI, less ghosting and noise), one
small broken frame in Megaera's introduction around Kratos, audio in time; but not much better than Unlock FPS, which
plays at the real 60 and more where frame generation holds the game at 36.

So `frame_generation = dlss` is turned off: the launcher no longer offers it and changes a file that has it to off,
and `main.cpp` takes it as off (`[gowa] frame generation off: NVIDIA DLSS frame generation is turned off in this
version`). The code stays: `D3D12_DLSSG_TEST=1` keeps `dlss` for a test, with the DLL fetch and checks as they were.
Reflex (`graphics.reflex`) and DLSS scaling stay. What would make it worth having: frame generation over a real 60 or
72 (Unlock FPS with it), and an on/off that waits for its inputs to be steady before it starts.
