# Multiplayer phase 2: a matchmaker of our own

Phase 1 (2026-11-22-multiplayer-phase1.md) ended with Quick Play's first message to the SAM server on 127.0.0.1:10070
and nothing to answer it. Phase 2 works out the wire format from samc's code and the game's handlers, and answers it:
`scripts/mp_sam.py` signs players in, opens the Match service and puts the players that search into one game world.
Two games on this PC (`mp_local.py --two`) now meet in one world, switch to its game mode, create the multiplayer game
and start the SAM transport, which stops at NP signaling: `sceNpSignalingActivateConnection` is a stub (phase 3).

## Running it

    py scripts\mp_local.py -- --no-launcher
    py scripts\mp_local.py --two --hdd0 <the dev_hdd0 the game uses> -- --no-launcher
    py scripts\mp_sam.py [--mode N] [--solo]          (the matchmaker alone)

`--two` starts a second game as another player (online id `PlayerB` unless `--name-b`), with its own dev_hdd0 in
`build/online/hdd0-b` (a copy of the first one's home folder; the game folders are junctions to the first one's) and
P2P port 3659. A second player without a TUS profile gets a copy of the first one's, so a tutorial done once is done
for both. `--mode N` puts every Quick Play match in game mode N; `--solo` reserves a world for a single player. The
matchmaker's log is `build/online/sam.log`. Everything stays on 127.0.0.1 as in phase 1.

## The wire

A frame is `u16 length` (counting itself), `u8 service`, `u8 message`, then the message's fields big-endian in class
order. Each message class has an encode and a decode method (the decoders are the third vtable slot: 0x00509E14 and
the 0x00508xxx/0x00509xxx family); a trailing field that is zero is sometimes left out (the connect message's
NPTestClientId, the session message's app version). The message types are two-byte descriptors that samc's static
constructors write to 0x00A37B0C..0x00A37B49 (read from a running game); the decoders per service are 0x0050C3B4
(connection), 0x0050BFE8 (Match) and 0x0050BCE8 (Profile).

| type  | direction | name                 | fields |
|-------|-----------|----------------------|--------|
| 00 00 | to us     | ClientConnect        | u32 multiplayer data hash, u32 0x80000817, u64 protocol 15, u32 default session, u16 n, u8, u8, n bytes NP ticket, [u64 NP test client id] |
| 00 01 | to game   | ConnectResponse      | u64 account, u32 session, u8 service, u8 response (0 = OK), u8 log level, u8 reason, [u16 app version] |
| 00 02 | both      | Session              | u32 session (0 asks for a new one), u8 service, [u16 app version] |
| 00 03 | both      | SessionEnd           | u32 session, u8 service, u8 reason |
| 00 04 | to game   | (not seen)           | u32, u32, u8 |
| 00 05 | to us     | (not seen)           | u16 n, u8, n bytes (built by 0x00509CAC) |
| 01 01 | to us     | Search               | u16 n, u8 min players, u8 max players, u8 kind (2), u8 flags, n bytes: the search head and players |
| 01 04 | to us     | WorldReport          | u32 world, u8 n, n x u64 account, n x u32, n x u8, n x u8 (built by 0x00400F2C from the roster) |
| 01 14 | to game   | (not handled)        | u32 n, u32 m, n x u32, m bytes |
| 01 15 | to game   | GameWorldReserved    | u32 world, u16 n, u8 result (MatchResultCode, 0 Success), n bytes: world head and players |
| 01 16 | to game   | GameWorldUpdate      | u32 world, u16 n, n bytes: u8 players, players x 0x6A |
| 01 17 | to game   | SearchUpdate         | u16 n, n bytes: u8 game mode, u8 players, players x 16-byte online id |
| 02 01, 02 02 | to game | Profile        | u16 n, u8, u8, 16 bytes, n bytes (Quick Play never opens the Profile service) |

Services: 1 Match, 2 Profile (the context's Data slot), 4 GameTracker (shares that slot). The game logs a session id
of 0 as an error, so ours start at 1001. 01 02 and 01 03 have descriptors but no encoder or decoder in the binary.

The connect response carries the ticket's account id back (the ticket body's first u64 field). The game then asks for
a Match session (`Session 0, service 1`), and our answer with a new id is "Session 1001 AppVersion 1 up". The connection
level handler (0x003FE364) sends service 1 and 2 messages to the Match and Data contexts once they have a session, takes
Session and SessionEnd itself, and reports anything else as "Junk msg from server".

## Search

    head  u64 the connect message's first eight bytes (data hash, 0x80000817): only equal ones are matched
          u32 0
          u8  game mode the player wants or, with flags 0x40, suggests
          u8  0
          u8  players in the search (a party's members), each 0x62 bytes after the head
          u8  flags: 0x40 = the mode is left to the matchmaker (Quick Play)
    player u64 account, SceNpId (36 bytes, online id first), 0x26 bytes of profile (0x00292050: rating, level,
          country code "us", NAT and skill bits), 16 bytes

The four bytes before the head are the mode's player range and two more: Quick Play picks a playlist entry at random
per search, and its range comes along. Seen so far:

| mode | name  | players |
|------|-------|---------|
| 1    |       | 6..8    |
| 2    | TFR4  | 4..4    |
| 3    | FFR8  | 6..8    |
| 4    |       | 4..4    |
| 5    | TCTF8 | 6..8    |
| 6    | THUN2 | 2..2    |
| 10   | FVS2  | 2..2    |

With flags 0x40 the game takes the world's mode whatever it suggested ("match maker success, requested game mode:4,
using game mode:10"), so our matchmaker puts Quick Play players together and picks a mode that one of them suggested
and that takes them all; after `--quick-wait` seconds (5) any mode known to take them. A search with a fixed mode only
meets the same mode.

## The reserved world

    head  16 bytes the game keeps in its match state (+0x0C, 0x00409250); what they mean is not known, random works
          u8  game mode (the game takes it when it left the mode to us; otherwise a different one is error 0x71)
          u8  players
          u8  flags: bit 1 = no players listed
    player the search's 0x62 bytes and eight of ours:
          +0x62 u8  1 = the host (the mesh manager, 0x001AE90C, starts hosting when its own entry has it)
          +0x63 3 bytes 0
          +0x66 u16 (not known, 0)
          +0x68 u8  peer index: every player its own; two equal ones are "New peer ... collides with ourself"
          +0x69 u8  (not known, 0)

The roster (samRoster.cpp, 0x001BCBA4) splits each entry into arrays: account, SceNpId, the peer index, the four bytes
at +0x62, the u16, +0x69, the 16 bytes at +0x52 and the profile. The game finds its own entry by account and stops with
"We got unexpected GameWorldReservedMessage" when it is not there.

## Two games

    world 7001, mode 10: ['PlayerA', 'PlayerB']
    A: match maker success, requested game mode:4, using game mode:10 / switch to match game mode: FVS2
       creating multiplayer game / created network interface (2 nodes) / start sam transport: mode = Match
       sceNpSignaling CreateCtx, P2P socket on 3658, Activate connection for Client ID <B> failed
    B: the same, P2P socket on 3659, Activate connection for Client ID <A> failed

Each game activates a signaling connection to every other player (a full mesh), then expects the peer to answer.
Two runtime changes were needed on the way (ps3recomp, branch gowa):

- `sceNpSignalingCreateCtx` refused with NOT_INITIALIZED: the firmware has no sceNpSignalingInit, and titles create
  contexts after sceNpInit. A context is now allowed after either (test_np_signaling_after_np_init).
- `sceNpSignalingAddExtendedHandler` and `sceNpSignalingSetCtxOpt` are not bound yet ("unresolved NID 0x50B86D94",
  "0x276C72B2"); the game goes on without them.

## Phase 3

NP signaling between two games on this PC: ActivateConnection to a peer's NpId through psnr (np_psnr.c already gives
each instance a P2P port and relays), the handler's events (established, dead), GetConnectionStatus/Info and the peer's
address and port, AddExtendedHandler and SetCtxOpt; then the game's own traffic over the P2P sockets. The signaling
error codes and event numbers in sceNpSignaling.h are worth checking against the SDK's then. Also open: what the world
head's 16 bytes and the entry's u16 and last byte are for, the WorldReport (01 04) the game sends from its roster, the
GameWorldUpdate we could send as players join, and "error in setting ExternalIP with 0" (MatchStatsHelper), which the
geo service may have answered.
