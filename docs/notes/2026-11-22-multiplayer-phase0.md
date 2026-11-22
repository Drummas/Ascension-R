# Multiplayer, phase 0: what the game needs to play online (2026-11-22)

A study of how God of War: Ascension goes online, to size the work of making its multiplayer run on servers of our own.
Nothing here talks to Sony's servers: those still run for the PS3 game, but they take only genuine PSN tickets, so the
port cannot use them and must never try. Everything below comes from the executable (strings, RTTI, the code around
them) and from three traced runs of the port. No multiplayer is built yet.

**In short:** the multiplayer is a peer-to-peer game (no dedicated game server) put together by Sony's own matchmaker,
"SAM", over a TCP connection the game protects with SSL code of its own. Before that, the game wants a PSN ticket, an
Online Pass, a game-update check, its configuration from PSN's Title Small Storage (TSS, encrypted) and a content
check against SCEA's DCDS server. The port can answer the console's side of all of that itself; the configuration has
to be written anew (Sony's copy is on PSN, not on the disc or in the updates), and the matchmaker has to be rebuilt from
the game's client code. The matchmaker is the large and uncertain part.

## The way in (the online gate)

The function at 0x0034BF10 walks a player into multiplayer and names each wait it can stop at:

`Waiting for network/IP` -> `waiting for NP Sign In` -> `waiting for TPPS` (the game update check, cellGameUpdate) ->
`waiting for EULA` -> `Requesting new NP ticket` / `waiting for NP ticket` -> `No Online Pass` ("An Online Pass is
required to play God of War: Ascension Multiplayer...") -> `waiting for boot-time TSS request to complete` /
`waiting for TSS` / `TSS in error state` -> `waiting for DCDS` -> `waiting for user to dismiss voice restriction dialog`.

The NP service (npService.cpp, states State_Initializing, State_GettingInfo, State_Online, State_Offline) asks for a
ticket at boot once signed in: service id `EP9000-BCES01741_00` on the EU disc. On GOT_TICKET it reads the entitlement
list (0x0035B468), the account id (`Received ticket of size: %d NP Account Id: %llu`, 0x0035B720) and starts the online
tasks (0x0035A114), among them the boot-time TSS request (0x0035DEC0).

## The configuration: PSN Title Small Storage

Every multiplayer setting is read through one function (0x0035E0A8) that returns a named block of the TSS data, which
sceNpLookupTitleSmallStorageAsync downloads (0x0035DC14). Its callers are the readers of `MatchConfig` (0x00425F98),
`EntitlementConfig` (0x004256BC), `telemetryconfig` (0x0042AE68), `PartyConfig`, `LobbyConfig`, `Playlist` /
`Playlist_Beta` and `VoiceConfig` (0x00517C70 to 0x0051B8C0). None of them is on the disc or in TPPS*.PSARC: the
disc's GAME.PSARC has only the MOTD texts and `PROFILE.DEFAULT.MP.INT6.JSON` (the multiplayer profile's template).

- **Encrypted.** 0x0035D684 decrypts the buffer (up to 64 KB, at +0x708 of its owner) before anything reads it
  (`Failed to decrypt TSS buffer.`). The cipher library's init (0x004DAEC0) registers Blowfish as algorithm 2 (8-byte
  blocks; its key schedule at 0x004DF398 uses the Blowfish P-array at 0x00689CC0); the TSS asks for algorithm 2 with
  option 4, a 16-byte key and an 8-byte IV, both in the executable at 0x0083B928. That option 4 is the chaining mode
  (CBC is the likely one), and the padding, are to be confirmed by a run. A tool that writes a TSS reads the key from the player's own
  GOWA.elf; it is not copied anywhere.
- **Laid out as named blocks.** Decrypted: a u32 version that must be 2, a block count at +0x0C, then 0x2C-byte entries
  from +0x10 (a 32-byte name, two u16 at +0x20 and +0x22, a u32 type at +0x28). `VersionMap` (type 1) is JSON that
  maps the game's app version to the blocks to use (its parser, 0x0035E1D0, reports `block '%s' app version '%s'
  index %d ...`).
- **What the blocks hold** (from the parsers' key names and their range checks, `error in retrieving %s val=%llu
  min=%llu max=%llu`):
  - `MatchConfig`, about 90 keys: `SAMServerHostAddr`, `SAMServerPort`, `SAMConnectTime`, `SAMRetryDelay`,
    `SAMTotalSearchTime`, `SAMDefaultMsgSize`, `SAMBwProbeTime`, `SAMTusTime`, `SAMStatsWaitTime*`, `Geo*`
    (`GeoServerAddr`, `GeoPort`, `GeoPath`, `GeoLookupPeriod`, `GeoTimeoutSecs`, the four result tokens), `Elo*`
    (skill rating: 21 keys), `GameMesh*` and `Mesh*` timeouts, `BandwidthProbe*`, `Stats*`, `GameTracker*`,
    `ShardStrategy` (`target%d` with `RangeLow`, `RangeHigh`, `Probability`), `TransportConfig`,
    `PartyTransportConfig`, `EnablePacketForwarding`, `EnableHostKickOut` and others.
  - `Playlist`: a `GameModes` array; each has `GameMode`, `Levels`, `GameModeSettings` (`ForceRespawnSeconds`,
    `AllowQuit`), `CountdownSettings` (`Countdown`, `UnskippableCountdown`, `SkipAmount`, `UnquittableCountdown`) and
    `MatchmakingSettings` (`NumRequiredPlayers`, `NumRequiredPlayersForSAM`, `...ToStartCountdown`,
    `...ToSustainCountdown`, `TotalCountdown`, `AvailableInQuickPlay`, `RequireExactTeamBalance` and six more).
  - `EntitlementConfig` (`GlobalEntitlements`, `FutureEntitlements`, `Entitlement`), and the party, lobby, voice and
    telemetry blocks, still to be read.

## DCDS (gowa.dcds.online.scea.com)

SCEA's content service, for the news (MOTD) and patches of multiplayer data. The client (0x00458CE8 onwards) POSTs an
XML `updateinfo-requestdata` (`text/xml`, to `%s://%s:%d%s/%s/%s`) with the NP ticket (`npticket`; `QueryWithNPTicket`
/ `QueryNoNPTicket`) and each entity's `fromversion`; the answer is an `updateinfo` document (`updates`, `entities`,
`files`, each file's `href`, `size`, `md5sum`, `delta`, `diffSignature`, `resultSignature`, `finalFileSize`). Files come
by GET (`.info`, `.rsltsig`, `.diffsig`) into `DCDS/dcds/DCDSTEMP`, then `DCDSFILES`: `DCDS-DL.PSARC`,
`DCDS-MANIFEST.TXT`, and `.DIFF` / `.PATCH.DIFF` patches of the multiplayer WADs. At boot the game writes its
bookkeeping into hdd0 `game/BCES01741-DATA/USRDIR/DCDS` (`dcds_hdd.txt`, `dcds_versions.txt` with the entities MOTD 1,
DATA-MP 1, DATA-SP 0, `dcds_checkpoint.txt`). A stand-in that answers "no updates" should be enough; the disc's MOTD
stays.

## Geo lookup (ipmapping-prod.online.scea.com)

SAM's `SamGeo` (0x003FEB98) opens a plain TCP connection to `GeoServerAddr:GeoPort` (defaults set at 0x003450F8:
`ipmapping-prod.online.scea.com`, `/ipmapping-rest/otgc/IPMapping/gow/location`) and reads `latitude`, `longitude`,
`countryCode` and `city` from the answer. Simple to stand in for.

## SAM, the matchmaker

Sony's shared network library (`z:/src6/Shared/Network/sam/`, namespace `net::sam`, with `sam::game` states) over a
client library ("samc", about 290 functions and 83 KB from 0x004FF000 to 0x00513000, with its own SSL code).

- **Transport: TCP.** samc opens a stream socket (0x005117CC), resolves the host with gethostbyname (0x005116BC) and
  connects (0x00511604). `SamStateStart::connect` (0x0040A560) logs `LocalPort, ServerAddr, ServerPort,
  EventQueueSize, MsgSize, NPTestClientId, SSL, NPLogonTime, defaultSessionId`.
- **SSL by default.** The SSL flag comes from byte 0x796 of the network settings object (0x009771C8), which its
  constructor sets to 1 (0x00345390) and no TSS key changes. samc then starts its SSL code (0x00510A88, mutexes
  `SAMSSL1`/`SAMSSL2`): an SSLv3-style implementation (the MAC pads 0x36/0x5C, the `CLNT`/`SRVR` finished labels,
  around 0x0051E000). The executable carries two certificates: AddTrust External CA Root (PEM, expired
  2020-05-30) and an SCERT Group "General 0" certificate signed by "SCERT Root Authority" (2005 to 2035). Since we
  build the executable, the flag can be cleared with one instruction and the matchmaker spoken to in the clear.
- **Login.** The first exchange carries the NP ticket; `SamStateStart::checkConnect` (0x0040AA8C) expects `Sam Client
  Connect Response serviceId, sessionId, acct, response, logLevel, appVer`, and the account id must be the ticket's
  (`Auth response acct id mismatch`).
- **Services and messages.** Four services with their own sessions: Match, Profile, GameTracker, Data
  (`SessionEndMessage for ... Service`). Named messages and events: `SearchUpdateMessage`, `GameWorldReservedMessage`,
  `ClientEventGameWorldReserved`, `ClientEventGameWorldUpdate`, roster updates; match states MATCH_IDLE, SEARCHING,
  FOUND, RETRY, INACTIVE; 27 `MatchResultCode`s (Success, Timeout, HostGone, GameNotFound, InvalidNATType, ...). The
  player's multiplayer profile (class XP and unlocks, as `profile.user.%i.%s.%s.json`) and the match stats
  (`samstats.json`) are JSON documents the game writes with a JSON library at 0x00512000 and keeps on the Profile and
  Data services. The wire format of the messages themselves is not known yet: no field names appear in the strings, so
  it is likely binary.
- **The game itself is peer to peer.** After a match is found, players connect through NP Signaling
  (sceNpSignalingActivateConnection with the peer's NP ID, 0x001B63F4) and play over UDP P2P sockets
  (`SamSocketPS3UDPP2P`, sys_net type 6): a game mesh with host migration and host or peer authority. A plain UDP
  socket class (`SamSocketPS3UDP`) is there too; what it is used for is not traced yet.
- **Also:** TUS (sceNpTusGet/SetDataAsync, `SAMTusTime`), telemetry over SCEA's OTG client (TCP, its own
  DNS-over-UDP lookup, a `CryptManager`; should be left unreachable, to be checked that it does not block), voice
  (cellVoice), presence and invites (sceNpBasic).

## The runs

Three runs to the title screen from a copy of hdd0 (`build\mp-hdd0`), every host name mapped to 127.0.0.1
(`PS3_NET_HOSTS=*=127.0.0.1`) and every destination outside 127.0.0.0/8 refused (`PS3_NET_LOOPBACK_ONLY=1`), with a
local listener on ports 80, 443 and 8080:

| Run | Settings | NP and network calls |
| --- | --- | --- |
| offline | the two above | sceNpInit, ManagerGetStatus OFFLINE, cellNetCtl not connected |
| signed in, no ticket | + `PS3_NET_ONLINE=1`, `PSNR_SERVER=127.0.0.1:36100` | GetStatus ONLINE, GetNpId, RequestTicket2 answered with a failed GOT_TICKET, sceNpBasicSetPresenceDetails2 (no handler) |
| signed in with a ticket | + `PS3_NP_TEST_TICKET=1` | RequestTicket2 (EP9000-BCES01741_00) answered with a 248-byte ticket, GetTicketParam(4) (account id), GetEntitlementIdList and TitleSmallStorageAsync (no handlers) |

In all three the title screen offers Latest News, Options and Single Player, and no Multiplayer. No HTTP request
reached the listener and no connection was tried: the game stops in its boot-time online tasks. The likely reason is
the TSS request, which has no handler and so ends with no data; to be confirmed once the port answers it. Nothing was
written into the real game folder (`game/BCES01741` is a junction to the installed copy).

## What the port answers today, and what it lacks

Of the game's 151 imports from the network libraries, 44 have no handler and return CELL_OK with nothing done:
cellGameUpdate (6: the TPPS wait), sceNpManagerGetEntitlementIdList / ById (the Online Pass), sceNpLookup
TitleSmallStorageAsync (the configuration), sceNpTus (7 of 10), sceNpSignaling SetCtxOpt, AddExtendedHandler,
TerminateConnection, sceNpBasic presence, messages and their dialogs (7), cellHttp cookies, SSL callback, request
headers and content length, transaction state callback (7), cellHttpUtil base64, cellSsl certificate names (3),
cellVoice notify queues (3), sys_net abort_socket and inet_ntop, sceNpDrmProcessExitSpawn2 and
sceNpCommerce2ExecuteStoreBrowse. cellHttp sends plain HTTP even for https (no TLS), which suits stand-in servers.

Added for this study (ps3recomp):

- `PS3_NET_HOSTS="name=ip;*.suffix=ip;*=ip"`: names the title looks up (gethostbyname, cellHttp) go to the first entry
  that matches; how the game's servers are pointed at stand-ins.
- `PS3_NET_LOOPBACK_ONLY=1`: connects, datagrams and HTTP requests to anything outside 127.0.0.0/8 fail, each
  destination reported once. For runs that must reach nothing else.
- `PS3_NP_TEST_TICKET=1` (signed in to psnr): a ticket of our own (NP ticket 2.1 layout, unsigned), its fields through
  sceNpManagerGetTicketParam. Nothing on the console side checks a ticket; servers of ours take it as it is.

The study's scripts stay outside the repository (`build\study\mp`): a cross-reference index of the PPU code that
follows SNC's way of making addresses (`lis` + `addic`, `ori rD, rS, 0` as a move), an RTTI-to-vtable reader, the
traced run with its listener, and the archive lister.

## What multiplayer needs, step by step

1. **To the lobby, on one PC.** The port answers the gate: no game update, the Online Pass owned (only that one; paid
   add-ons are not handed out), the EULA, the ticket, and the TSS from a file of ours. A tool writes that TSS
   (Blowfish with the key from the player's own executable, the block table, VersionMap, MatchConfig, Playlist,
   EntitlementConfig and the rest, each value inside the parser's ranges). Small stand-ins answer DCDS ("no
   updates") and the geo lookup. SAM's SSL flag cleared. Done when the Multiplayer entry shows, the lobby opens and
   the game's first message to SAM reaches a local listener. About one to two weeks.
2. **The matchmaker.** Work out samc's wire format and the messages the game handles (login, the four services'
   sessions, search, roster, game world reserve and update, profile and stats storage) from its code and from what it
   sends, then a server that can match two players in one mode. The biggest and least certain part: three to six
   weeks.
3. **Playing.** NP Signaling through our server (peers' addresses from their NP IDs), the P2P mesh on psnr's NAT
   traversal and relay, first two copies on one PC, then two PCs. Two to four weeks.
4. **The rest.** Parties and invites, TUS, voice, telemetry kept off, a public server, docs, a beta release. Two to
   four weeks.

All in, about two to four months of steady work, most of the spread being the matchmaker's size. Players on the port
would play each other only, never PS3 players on Sony's servers.

## Open questions

- Which chaining mode Blowfish mode 4 is, and the padding (a run with a TSS of ours answers it).
- Whether the title's Multiplayer entry waits on the TSS, on the whole gate, or on something else.
- samc's message framing and how many message types the game sends and handles.
- What the plain UDP socket (`SamSocketPS3UDP`) and the `SamFBAProcessor` are for.
- Whether telemetry or DCDS failures stop the lobby.
- The values Sony's TSS held (match sizes, countdowns, Elo constants): ours will be guesses within the code's ranges
  unless a copy turns up.

## Phase 1

Done the same day (2026-11-22-multiplayer-phase1.md): the TSS cipher is Blowfish OFB, the Multi-Player entry is on
the title's carousel (right), and the game now gets through the gate into the lobby and opens a plain TCP
connection to a matchmaker of ours.
