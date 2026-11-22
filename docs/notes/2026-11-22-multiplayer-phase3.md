# Multiplayer phase 3: two games play a match peer to peer

Phase 2 (2026-11-22-multiplayer-phase2.md) ended with two games on this PC in one game world from our matchmaker, each
failing at `sceNpSignalingActivateConnection`, a stub. Phase 3 gives the runtime NP signaling and a server for it, adds
the Playlist block the match needs for its levels, and the two games now connect to each other, load the same arena
and play the match: one hosts, the other joins, the rounds and the score are the same on both screens.

    py scripts\mp_local.py --two --hdd0 <the dev_hdd0 the game uses> -- --no-launcher

`mp_local.py` runs the signaling server (ps3recomp `tools/np_signaling_server.py`) beside the matchmaker and points
both games at it (`PS3_NP_SIGNALING_SERVER=127.0.0.1:36101`). The second game runs without mods: both games would pack
them into the one `build/mods/.built` while the first has its archive open, and two games started that way have hung
on their first load ("waiting to unload hero wad").

## How the game uses signaling

The SAM transport (samNpSignalingMgr.cpp, 0x001B5304..0x001B6538) calls, in order: `sceNpSignalingCreateCtx` with no
handler, `sceNpSignalingAddExtendedHandler` (its handler 0x001B673C, OPD 0x0082D488), `sceNpSignalingSetCtxOpt(ctx, 1,
0)` (no bandwidth probe), then `sceNpSignalingActivateConnection` to every other player in the world by NP ID (a full
mesh), and later `GetConnectionStatus` (the peer's address and port), `GetConnectionInfo`, `GetLocalNetInfo`,
`DeactivateConnection`/`TerminateConnection` and `DestroyCtx`. It takes 0 for "no context" and "no connection", so ids
start at 1. The extended handler gets every event and queues it for the connection manager:

| event | value | the game's kind |
|-------|-------|-----------------|
| DEAD | 0 | 1 |
| ESTABLISHED | 1 | 5 |
| EXT_PEER_ACTIVATED | 10 | 4 |
| EXT_PEER_DEACTIVATED | 11 | 2 |
| EXT_MUTUAL_ACTIVATED | 12 | 3 |

These are the SDK's numbers; the runtime's old header had DEAD 2 and ESTABLISHED 3, and its error codes were off too
(the game tolerates `0x80022A0E`, CONN_NOT_FOUND, from Deactivate/Terminate; the old header gave CONN_NOT_FOUND as
`0x80022A07`). Both are fixed.

## The runtime (ps3recomp, branch gowa)

- `tools/np_signaling_server.py`: every instance says HELLO with its online id and P2P port; ACTIVATE of a peer answers
  with the peer's address (as the server sees it) and P2P port and tells the peer (ACTIVATED); DEACTIVATE and leaving
  tell the peer too. The protocol is in `libs/network/np_signal_client.h`.
- `sceNpSignaling.c`: contexts, connections by NP ID, events through `cellSysutilQueueGuestCallbackArgs` (delivered on
  the title's next `cellSysutilCheckCallback`, which also pumps the server through np_psnr's ticks). ESTABLISHED comes
  `PS3_NP_SIGNALING_DELAY_MS` (500) after the server's answer; an activation the server cannot answer within 15
  seconds is DEAD (TIMEOUT), a peer that leaves DEAD (TERMINATED_BY_PEER). An activation is sent again every second
  until the server confirms it, so a peer that activated first still hears of ours (MUTUAL on both sides).
- `sys_net`: `inet_ntop`, which the game calls as the match starts.

The game's own traffic then goes over its DGRAM_P2P socket straight to the peer's P2P port (3658 and 3659 here).

## The Playlist block

With signaling working, the host stopped at "No valid levels in level cycle." / "Game Mode No Longer Available": a
match takes its level from a cycle table (0x008BF71C, allocated by 0x00142030) that only the TSS `Playlist` block
fills (parser 0x00519794): `{"GameModes": [{"GameMode": name, "Levels": [names]}]}`, optional MatchmakingSettings,
countdowns and GameModeSettings (ForceRespawnSeconds, AllowQuit). Only levels the mode itself allows are kept. The
names come from the game's own tables, read from a running game in the multiplayer lobby: modes at 0x00977DD0, levels
at 0x00977DB4, the levels each mode allows at 0x00977DC0.

| mode | Search id | levels |
|------|-----------|--------|
| TFR8 | 1 | Bog8TFR Des8TFR Lab8TFR Try8TFR Eng8TFR |
| TFR4 | 2 | Oly4TFR Hrc4TFR Pht4TFR Per4TFR Fry4TFR |
| FFR8 | 3 | Bog8FR Lab8FR Try8FR Des8FR Eng8FR |
| FFR4 | 4 | HRC4FR PHT4FR Per4FR Oly4FR Fry4FR |
| TCTF8 | 5 | Bog8CTF Lab8CTF Try8CTF Des8CTF Eng8CTF |
| THUN2 | 6 | Des2GNT Hrc2GNT Phi2GNT Per2GNT Lab2GNT Oly2GNT |
| THUN1 | 7 | Oly1GNT Phi1GNT Des1GNT Hrc1GNT Lab1GNT Per1GNT |
| FVS2 | 10 | Del2VS Flam2VS Spa2VS Cyn2VS |

`online/tss/Playlist.json` has them all. The game reads the TSS once at boot and parses the Playlist then, against the
single-player tables, which lack FVS2 and several levels ("Parse error: ... non-existent level"); it parses it again,
without a word, once the multiplayer tables are in, and the match finds its levels. The boot-time errors are harmless.

## Runs

Two games, Quick Play on both, nothing else touched: the matchmaker put them in FVS2 (both had suggested four-player
modes, so after five seconds the known two-player mode), signaling connected them both ways, the first became the host
("*** host ***", node 0) and the second joined ("*** guest ***", node 1), both loaded Flam2VS ("game start: Flam2VS"),
and the match ran with the same timer and score on both screens. Another run put them in THUN2 (two players against
the gods' minions), which ran until both screens said "You Lose!" (nobody was playing). About 20-30 fps each with both
on this PC.

## Still open

- Players on other machines: the signaling server hands out the address it sees, so a player behind a router needs
  its P2P port forwarded; psnr's NAT traversal and relay are not on this path.
- The world head's 16 bytes, the entry's u16 and last byte, and the WorldReport (01 04) the game sends empty right
  after the world is reserved; GameTracker sessions (service 4) open at the match start and send nothing yet.
- "error in setting ExternalIP with 2130706433" (MatchStatsHelper) after a match: the geo service may answer it.
- The match's end and the return to the lobby, a full round of play with input on both sides, and more than two
  players.
