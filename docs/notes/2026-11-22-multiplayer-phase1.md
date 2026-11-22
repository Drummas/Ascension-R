# Multiplayer, phase 1: through the online gate to the matchmaker's door (2026-11-22)

Phase 0 (2026-11-22-multiplayer-phase0.md) mapped what the multiplayer wants. This phase makes the game go all the way
on one PC, against nothing but stand-ins on 127.0.0.1: from the title screen through the online gate into the
multiplayer lobby, and from the lobby's Quick Play into a plain TCP connection to a matchmaker of ours, where the game
sends SAM's first message. Nothing answers it yet: that is phase 2.

## Trying it

    py scripts\mp_local.py -- --no-launcher

builds our TSS (scripts\mp_tss.py from online\tss), starts the game signed in with a ticket of our own, every host
name it looks up pointed at 127.0.0.1 and nothing let past this PC, and records what reaches the matchmaker and geo
ports (build\online\listen.txt). On the title screen **right** turns the carousel from Single Player to
**Multi-Player**: the entry was never hidden (phase 0 thought it was). A new profile goes to the multiplayer tutorial
first; with a finished one the lobby opens, and Quick Play shows "Searching for Match" and connects.

## What it took

- **The game's own log.** func_001C2784 is a printf-style log with 637 callers, emptied in the release build.
  `gowa_game_log` (port/online.cpp, an instruction hook in scripts/ppu_hooks.json) formats and prints each line as
  `[game] <level> <text>` with `GOWA_GAME_LOG=1`. Every step below was read from it.
- **The TSS: Blowfish in OFB mode.** The cipher library's "algorithm 2, option 4" is Blowfish OFB (not CBC, which was
  the guess): a CBC file of ours came out of the game's own decryption as exactly our file under OFB, so the key and IV
  at 0x0083B928 were right from the start. `gowa_tss_seen` prints the decrypted header. Seventeen blocks are asked for
  by name and version (func_0035DF34): MatchConfig 10, Playlist 7 (Playlist_Beta when a beta flag is set),
  ProfileConfig 3, XpConfig 3, DcdsConfig 7, LobbyConfig 2, UiConfig 2, ProtocolConfig 2, telemetryconfig 2,
  partyconfig, EntitlementConfig, TssConfig, CombatConfig, KillSwitchConfig, SyncLoadConfig, VoiceConfig (1 each) and
  motd_<language> 1. Most readers take only the keys that are there and keep the game's own values for the rest;
  MatchConfig takes all of its keys or fails (each in a range, error codes logged). Ours (online\tss) has 9 blocks:
  MatchConfig with the values the game's own constructor of those settings starts from (func_00610768: Elo constants,
  mesh timeouts, stats smoothing) and our addresses (the four SAM targets and the geo server on 127.0.0.1), DCDS off,
  no global entitlements, and empty UI, XP, voice, kill-switch and TSS settings. `mp_tss.py dump` shows a file's blocks.
- **The gate's answers.** In ps3recomp (778e1c48): Title Small Storage from `PS3_NP_TSS_FILE`; TUS data slots as the
  SDK has them, kept as files under `PS3_NP_TUS_DIR` (the multiplayer profile is slot 1, match stats slot 2); no
  entitlements; the game update check finding no update. In the port: the Online Pass. The gate asks for it as bit 0
  of the add-on content mask (func_002CA2A8), which the content scan sets when /DLC/DLC0 holds a licensed INDEX.EDAT;
  `gowa_online_pass` reports it there, as Sony stopped requiring passes for its own games in 2013
  (`GOWA_ONLINE_PASS=0` leaves the mask as found). Paid add-ons are not touched: the game asks PSN for 16 of them
  (`EP9000-BCES01741_00-JUDGE0`, `-MERCES`, `-CHAMPS`, `-ARTEM0`, ...) and gets "not owned".
- **The profile and the tutorial.** The profile is JSON (`{"profile": {"version", "last class", "tutorial complete",
  "classes", "scores", "upgrades", ...}}`) in TUS slot 1; an empty slot loads the disc's
  PROFILE.DEFAULT.MP.INT6.JSON, whose tutorial is not done, so a new player plays the multiplayer tutorial (a local
  match, TutMode in TUTBAS) before the lobby. The lobby saved a 3776-byte profile back.
- **SAM in the clear.** Bytes 0x796 and 0x797 of the network settings are SSL and a threaded SSL transport on top of it.
  samc's func_0050CB14 builds plain TCP only with both clear (SSL off with 0x797 still set is its error 28), so
  `gowa_sam_ssl` clears both; `GOWA_SAM_SSL=1` keeps them.
- **On the way, not in the way.** The bandwidth test (sceNpUtilBandwidthTest*) times out and the game moves on. The geo
  lookup connects to GeoServerAddr:GeoPort and sends the path alone (43 bytes,
  `/ipmapping-rest/otgc/IPMapping/gow/location`), then waits; with no answer it logs "GeoLocation failed" and goes on.
  cellNetCtlGetInfo for the Wi-Fi signal strength (code 11) fails on our wired connection, logged and harmless.

## The first message

276 bytes on the TCP connection to 127.0.0.1:10070, sent once the connection is up:

    +0x00 u16 0x0114        its length
    +0x02 u16 0
    +0x04 u32 0x2A5752D1    the multiplayer data hash the game logs ("data hash is 2a5752d1")
    +0x08 u32 0x80000817
    +0x0C u64 15            the protocol version samc insists on (func_0050B438 rejects any other)
    +0x14 u32 0
    +0x18 u16 0x00F8        the ticket's length, 248
    +0x1A u16 0
    +0x1C the NP ticket (our 2.1 test ticket)

When the connection closes without an answer the game reports "Matchmaker Error 2:198:20" and returns to the lobby.
What it expects back (SamStateStart::checkConnect: serviceId, sessionId, the ticket's account id, a response code,
logLevel, appVer) is where phase 2 starts.

## Runs

All with `PS3_NET_LOOPBACK_ONLY=1` and every name on 127.0.0.1: the title (Multi-Player on the carousel), the gate
(ticket, TSS, update check, EULA, pass), the tutorial from an empty profile, the lobby from a finished one, Quick Play
to the matchmaker connection, and `mp_local.py` repeating the last with input from `PAD_SCRIPT`. Nothing was written to
the installed game folder.

## Phase 2

Done the same day (2026-11-22-multiplayer-phase2.md): the SAM wire format and scripts/mp_sam.py, a matchmaker that signs
players in, opens the Match service and puts two games on this PC into one game world; they stop at NP signaling.
