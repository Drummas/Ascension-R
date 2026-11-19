# Sound behind the picture: the device queue at 15 ms (2026-11-20)

Issue #31: on 0.2.0, the impacts of the opening fight with Megaera are heard a little after they are seen, every
time. 0.2.0 had already ended the shader stops that pulled sound and picture apart before: in the report's session no
shader was compiled while the game played (all 39,597 from the prebuilt file), and the video holds 59.9-60 fps. What
is left is a fixed delay on the sound's way out.

## The way out

- **The title's ring**: eight blocks of 5.33 ms. With `AUDIO_RATE=1` the ring report shows the title writing a block
  again within a block of its being read (`written after read` ~750 of the ~938 blocks read in 5 s, every block
  after the one read already full), so a block it writes is heard about seven blocks, ~37 ms, later. This is the
  title's own, as on a PS3.
- **The device queue**: ps3recomp's mixer takes a block every 5.33 ms by the performance counter and keeps the
  WASAPI stream's queue near `AUDIO_PACE_MS` as a jitter buffer (`libs/audio/cellAudio.c`, since 2026-10-29). It was
  30 ms: heard as 30 ms more, which a PS3 does not have.
- **Windows' audio engine**: shared mode, a 10 ms period (3 ms at least on this PC's Realtek output), and the APOs
  unless **Bypass sound effects** is on.
- **The device**: the reporter's is the S/PDIF output of a USB audio device, so a receiver or a DAC adds its own.

The picture, on the other side, goes out sooner than a PS3's on a television: no VSync wait (the reporter's is
off), a 144 Hz monitor.

The reporter's video could not give a number: the mix is dense (music, voice, effects), and the recorder's own sync is
not known. At the clearest hit (the camera's shake at 14.63 s) the high crack starts with the shake's first frame and
a low thud comes ~70 ms later, which may be how it was made.

## The change

- **`AUDIO_PACE_MS` defaults to 15**, the least it takes (it was 30). The 30 had been set against blocks taken in
  pairs, not against a smaller queue.
- **The log says the way out** when the stream opens: `[cellAudio] the way out: the queue kept near 15 ms, the engine's
  period 10.0 ms (3.0 ms at least), the stream's latency 0.0 ms as Windows gives it; what the device adds after that
  Windows does not say`. `GetStreamLatency` gives 0 on many shared-mode streams, as here.
- `AUDIO_PACE_MS=30` (or any value from 15) brings a bigger queue back; on 0.2.0 the same variable already lowers it.

## Checked

On an i5-12400F (6 cores, 12 threads, like the reporter's Ryzen 5 5600X), `AUDIO_RATE=1`:

| run | queue | gaps in the title's ring | device underruns | frames dropped |
|---|---|---|---|---|
| the opening cinematic | 30 ms | 0 | 0 | 0 |
| the opening cinematic | 15 ms | 0 | 0 | 0 |
| the parasites' fight replay (`build\probes\fight.pad`), 145 s | 15 ms | 0 | 0 | 0 |
| the opening cinematic, the new default | 15 ms | 0 | 0 | 0 |

## Not checked

- A PC with fewer cores, or one whose audio driver wakes late: 15 ms leaves less room for the mixing thread to be
  late before the device runs dry. `AUDIO_PACE_MS` takes a bigger queue back.
- How much of the reporter's delay is the S/PDIF chain after the PC.
- A low-latency shared-mode stream (`IAudioClient3`, a 3 ms period here) would take a few ms more off; not tried.
