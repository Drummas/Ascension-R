# Multiplayer: the node from the launcher, and who is online

After phase 7 (2026-11-22-multiplayer-phase7.md) the node of Auto started at Play, so it began to look for players
only as the game started, and nobody could see whether anyone else was around. Now the node runs as soon as the
launcher shows Auto, and the Multiplayer tab lists the players the node knows of and what each is doing.

## The node from the launcher

`port/multiplayer.cpp` starts the node from a snapshot of the settings (`Args`: mode, name, the host, the community
nodes, the GOWA.elf, every switch, and `sig`, all of them in one string), so the launcher can start it on a thread of
its own:

- `gowa_online_begin(window, message)`: on Auto, the node of the settings as they are, unless that one runs or starts
  already; on anything else none (Host and Join still start at Play). A message to the window when the start ends.
- `gowa_online_stop()`: a start under way called off; a running node asked to stop (it says goodbye, below), ended a
  second later whatever it did, and the variables its game.env put in taken out of the environment.
- `gowa_online_status()`: none, running, starting, or the last start failed and why.
- `gowa_online_start()` (Play, and main when there is no launcher): waits for a start under way; a running node whose
  settings are those of now is the one the game takes; else it starts one as before.

The launcher calls `online_sync` (the online settings into ps3_settings, then `gowa_online_begin`) when its window
opens, when Multiplayer or one of its switches changes, when typing into the online ID, the host's address or the
community nodes ends, and on Defaults. Quit, or the game's end, runs the stop through `atexit`; a crash or a kill
leaves the other nodes a minute of silence before they drop it.

## Who is online

Every node says what its player is doing: ready (the node runs: the launcher, or the game outside the multiplayer
menu), lobby (the game is connected to its matchmaker: the multiplayer menu), searching (Quick Play), playing (from
the world to the end of the match: the game's GameTracker session, service 4, which mp_sam's matchmaker now reports
to its subclass, or the game leaving). It goes in hello, in every ping (and at once when it changes) and in the lists
nodes tell each other. A node asked to stop (`online\node.stop` appears) sends `bye` first, and the others take it off
their lists at once.

The node writes `online\players.txt` when it changes: `me <reachable> <state> <count>`, then
`player <state> <how> <name>` for each player it knows of: reached itself (direct), through another node (through), or
only told of by another node (heard). Community nodes are not players.

The Multiplayer tab shows the node (on and how others reach it, starting, or why it did not start) and Online now:
each player's name, what they are doing and how they are reached, ten at most and how many more. The Play tab's Your
setup says Multiplayer: Off, Host, Join, or Auto with the count; a click goes to the tab.

## Runs

- tests/test_mp_p2p.py: a node's list follows the other player through ready, lobby (its game connects), searching,
  playing (the world), lobby again (its GameTracker session ends) and ready (its game leaves); a player behind
  another node shows as through, a community node not at all; a node asked to stop is off the other's list at once.
- Two launcher windows on this PC, Auto, from settings copies (LAN only): both nodes started without Play and each
  listed the other within seconds; window A showed Online now: 1, PlayerB online; A switched to Off and was gone from
  B's list at once; after Quit no node ran. The real settings file was not touched.
- `GOWA_LAUNCHER_SHOT`: the tab with a made-up list (shot 25) and the Play tab's line (shot 26).
