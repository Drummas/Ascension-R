# Multiplayer phase 4: players on other machines, a match to its end

Phase 3 (2026-11-22-multiplayer-phase3.md) ended with two games on one PC playing a match peer to peer, each at the
address the signaling server saw it at. Phase 4 lets players on other machines and other networks play: the P2P
socket learns how it looks from outside, peers punch toward each other and fall back to a relay through the server,
the network guard lets the server and the introduced peers through, and two scripts run the server and a player.
Matches now run to their end: both games go back to the lobby and the next match starts on the next level.

## Running it

On the machine that hosts (any player's, or a server elsewhere):

    py scripts\mp_server.py [--public-ip A.B.C.D] [--players N] [--mode N]

It runs our matchmaker (scripts/mp_sam.py) and the runtime's signaling server on every address and logs to
`build\online\server.log`. Players reach it at TCP 10070 (matchmaker), TCP 10012 (geo) and TCP and UDP 36101
(signaling and relay). Behind a router, forward those to the host and give `--public-ip`, the address players
elsewhere use.

Every player, the host included:

    py scripts\mp_play.py --server <host> --name <online id> [--relay] [-- <game arguments>]

It builds our TSS with that host as the matchmaker and geo service (`mp_tss.py build ... --server`), signs the game
in with a ticket of our own and starts it with every name pointed at the host. With `PS3_NET_LOOPBACK_ONLY` and
`PS3_NET_ALLOW=<host>`, nothing is reachable but this PC, the host and the players the signaling server introduces.
Every player needs an online id of their own. A player on the host machine itself can use `--server 127.0.0.1`.

The peers' own traffic goes to each other's P2P port (UDP 3658; `--p2p-port` for another). Forwarding it is not
needed: when the routers do not let a direct path through, the relay carries it.

## NAT traversal and the relay (ps3recomp, branch gowa)

The signaling server now listens on UDP at its TCP port too, and WELCOME carries a token, the UDP port and whether it
relays. `sceNpSignaling.c` hooks np_psnr's P2P socket (`np_psnr_set_p2p_hooks`): its own datagrams start with
`NPSG` and never reach the title.

- PROBE (online id, token) from the P2P socket: the server answers PROBE_REPLY with the address and port it saw, and
  tells every linked player (MOVED) when that differs from what it handed out before. A probe with the wrong token
  is ignored.
- PUNCH to a peer's endpoint every 200 ms for two seconds, then every second; a PUNCH answered with PUNCH_ACK makes
  the path direct. A PUNCH from an unexpected address (a NAT that maps per destination) moves the peer there.
- No direct path after three seconds: the title's datagrams to that peer go to the server wrapped in RELAY, and come
  back from it as RELAYED, unwrapped and attributed to the peer's address, so the title sees one peer either way.
  `PS3_NP_SIGNALING_RELAY=1` always relays (no punches); `mp_server.py --no-relay` turns the relay off.
- ESTABLISHED (and MUTUAL) wait for one path or the other; DEAD (PEER_UNREACHABLE) after 15 seconds of neither.

Where the server hands a player out (`Player.where_for`):

| the player | the viewer | address handed out |
|------------|------------|--------------------|
| same public address as the viewer (one router) | | its own network address, from HELLO |
| elsewhere | | the endpoint its probe came from (its router's mapping) |
| on the server's network | elsewhere | `--public-ip`, else the server's address |
| on the server's own machine (loopback) | not | the address the viewer reaches the server at |

The last row came out of the LAN run below: a host playing through `127.0.0.1` had been handed to the other player
as 127.0.0.1.

`sys_net`: with `PS3_NET_LOOPBACK_ONLY`, `PS3_NET_ALLOW` lists addresses that pass too (one address or a /n
network, up to 16), and every peer sceNpSignaling introduces passes on P2P sockets only (`sys_net_allow_peer`).

## Runs

Two games on this PC, Quick Play on both, `--mode 6` (THUN2):

- Relay always (`mp_local.py --two --relay`): the signaling server logged "relaying PlayerA -> PlayerB" and back,
  both games "through the relay", one host and one guest. Three matches in a row: Des2GNT for three minutes, then
  "server sync lobby" / "go to game lobby" on both, the lobby, Oly2GNT, the lobby again, Phi2GNT. Each match opens
  two GameTracker sessions (service 4) at its start and ends them at its end.
- Through the LAN address: `mp_server.py` on every address, the first game through 127.0.0.1, the second through
  this PC's LAN address, so each is handed the other at the LAN address: both "direct", nothing relayed, nothing
  refused by the guard, two matches to their end and the third under way when the run stopped.

## The lobby entry that stalled

Midway through, every lobby entry stopped at "waiting for wad info restart", one game or two, and the phase 3
runtime did the same, so it was not this phase's code. The WAD manager (FUN_00042E28) was in job 4 (FUN_0003FED4,
the R_Lang_<lang>_MP reload), stage 2, which waits for the audio streamer to be idle (func_0x003A1634:
0x009B2270 == 0 and 0x009B26A4 == 0). The streamer sat in state 2 (FUN_0039D3D0: a stop asked for, waiting for its
read on the stream at 0x009B1E30 to finish, FUN_002C4FA4), and that read never finished. Moving the FIOS disc cache
(/dev_hdd1, `<cache>/BCES01741/fios/cache.dat` and `cache.idx`) aside ended it: the game made a new one and went
into the lobby. That cache had been written by two games at once all day. `mp_local.py` now gives each game its own
cache partition (`PS3_HDD1_ROOT=<out>/hdd1`, `<out>/hdd1-b`), its own shader cache and -DATA folders as before, and
the runs above passed that way. Whether a game stopped while writing the cache can break it too is not known.

## Still open

- More than two players: the matchmaker puts a group in one world (`--players N`; three need `--mode` too, as no
  known mode takes three) and the signaling server links every pair (tests with four), but no game has played with
  more than one other: this PC runs two games at most (12 threads, 16 GB).
- Two networks for real: the punch and relay paths have run here and in the tests, not across two routers.
- "saving stats failed, IsIdle:0" after every match on both games (FUN_00343C24 / FUN_00343D60: the SAM stats
  object at 0x0083B868 is not idle, "SamStatsSaveFailed"); the stats service is not answered.
- The world head's 16 bytes, the entry's u16 and last byte, the WorldReport (01 04) sent empty; "error in setting
  ExternalIP" after a match.
- Firewalls: Windows may ask to let the game (its P2P port) and Python on the host (the server's ports) through. A
  player whose P2P port stays blocked is relayed; a host whose ports stay blocked is not reached from elsewhere.
- The launcher: a Multiplayer page with the host and the online id instead of the scripts.
