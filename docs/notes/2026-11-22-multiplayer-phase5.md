# Multiplayer phase 5: the launcher's Multiplayer tab

Phase 4 (2026-11-22-multiplayer-phase4.md) played across machines through two scripts. Phase 5 puts that in the
program: the launcher has a Multiplayer tab, and Play starts the matchmaking side itself with the Kit's Python, so a
player opens the game, sets an online ID once, picks Host or Join, and plays. Phase 6 adds finding players without a
host (the BitTorrent DHT); this phase's node is where that goes.

## The tab

| row | setting | what it does |
|-----|---------|--------------|
| Multiplayer | `[online] mode` = off, host, join | Host: this PC runs the matchmaker and the signaling server, for its own game and the players who join it. Join: play through a host's PC. |
| Online ID | `name` | The player's name in the game, typed in (3-16 letters, digits, - and _, starting with a letter: the runtime's rule). |
| Host's address | `server` | To join: an IPv4 address or a name. |
| Always through the host | `relay` | The game's datagrams always through the host's relay. |

Two settings have no row yet: `port` (the P2P port, 3658) and, for a host, `game_mode` and `players` (every Quick
Play match in one mode; wait for that many players).

Under the rows: on Host, the addresses players on this PC's network join at (`gowa_online_lan`: each IPv4 address
of an adapter that is up, with its name, loopback and 169.254 left out), what to forward for players on the
internet (TCP 10070 and 10012, TCP and UDP 36101) or to use a virtual network instead; that the players one plays
with see one's address; and why the last Play could not start multiplayer, if it could not.

The online ID and the host's address are the launcher's first text boxes: a click takes the keys (`s_edit`), the
characters come as WM_CHAR (a name takes letters, digits, - and _; an address letters, digits, - and dots; anything
else is not taken), Backspace, Ctrl+Backspace (all of it), Ctrl+V; Enter, Esc, Tab or a click elsewhere end it. A box
whose value will not do has a red edge. Defaults leaves them as they are.

## Play

`port/multiplayer.cpp`: Play saves, then `gowa_online_problem` (no online ID, no host's address, no Kit Python: a
toast, and the tab), then `gowa_online_start`:

1. `scripts\mp_node.py host|join --name ... --elf <the settings' GOWA.elf> --dir <settings folder>\online` with the
   Kit's Python (`kit\python`; in a build tree the .venv's, as mods.cpp finds its packer), in a job that is killed
   when the program ends.
2. The node builds our TSS from the player's GOWA.elf (the host's address in MatchConfig for join; this PC's for
   host) and writes `game.env`: every variable the runtime's network and NP read (mp_play.py's `game_env`), the ones
   a run leaves out empty, so they are cleared.
3. The program waits for `game.env` (about a second; 30 at most), puts each variable into its environment with
   `_putenv_s` before anything reads it, and starts the game. A node that stops writes `node.error`, which the tab
   shows.

A host's node then runs the matchmaker and the signaling server on every address until the game ends; a joining
one checks the host answers, for its log, and ends. `--no-launcher` takes the same path from the settings (`--set
online.mode=host`); a script that set the network up itself (`PS3_NET_ONLINE` in the environment: mp_local.py,
mp_play.py) wins.

The node's folder, `online\` beside the settings: `tss.bin`, `np_tus\` (the multiplayer profile), `node.log`,
`node.out` (the Python's own output).

## The Kit

The node and what it imports (`mp_node.py`, `mp_play.py`, `mp_tss.py`, `mp_sam.py`, ps3recomp's
`np_signaling_server.py`) and `online/tss` go into the Kit (`KIT_PLAY` in gowa.py), but not into its id: none of them
goes into the DLL, so a Kit with a new node keeps its id and nobody builds the game's code again for it.

## The problem report

Since phase 4 a session's log names the other players' addresses, and a report is posted where anyone reads it. The
report now writes every IPv4 address as `<private ip>` or `<ip>` (loopback and 0.0.0.0 stay; four numbers of 0-255,
so a version such as 32.0.21013.1000 stays too) and the host's name as `<host>`, and adds the node's log as
`multiplayer-node.log`.

## Runs

- Two games on this PC through the settings alone, no script: A `online.mode=host`, `game_mode=6`; B from a settings
  file of its own (its own `online\`), `mode=join`, `server=127.0.0.1`, P2P port 3659. Both signed in by name, the
  host's node put them in one world, signaling connected them directly, one host and one guest, two THUN2 matches to
  their end and back to the lobby. Killing the games took the node with them.
- The tab driven by window messages on a copy of the settings: Join, an online ID with Backspace and a character it
  does not take, an address with a space, Enter (no game started), Save: the file had `mode = join`, the name and
  the address as typed, without the characters that were not taken.
- A report from a session log with a LAN and a public address and a driver version in it: both addresses hidden,
  the version kept.
- `GOWA_LAUNCHER_SHOT`: the tab on Host, and on Join with the address being typed and a start that failed (shots 22,
  23).

## Still open

- Phase 6: players find each other with no host (the node on the DHT), and phase 7: NAT traversal and relaying
  between nodes.
- The tab has no rows for the P2P port or a host's game mode and player count.
- More than two players, two real networks, the stats save after a match.
