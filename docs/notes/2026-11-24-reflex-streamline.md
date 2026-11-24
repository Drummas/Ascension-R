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
