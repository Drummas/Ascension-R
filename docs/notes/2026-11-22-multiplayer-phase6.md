# Multiplayer phase 6: players find each other with no host

Phase 5 (2026-11-22-multiplayer-phase5.md) put Host and Join in the launcher; somebody still had to host. Phase 6
adds Auto: every player's game runs a node of its own, the nodes find each other as torrent clients find a
torrent's peers, and the ones whose games search together agree on a game world among themselves. Nobody runs a
server.

## The node (scripts/mp_p2p.py)

`mp_node.py auto` (what Play starts on Auto) runs it. On this PC it is the game's matchmaker (SAM) and signaling
server, bound to 127.0.0.1, for its own game only; the TSS names it as the matchmaker. Its ports are the usual ones
(10070, 10012, 36101) or, when another game's node on this PC has them, any; the second game on one PC then takes P2P
port 3659 or the next free one. With the other nodes it talks on one UDP socket (36102, or any), which the DHT client
shares:

- `b"ASCR" 1 <JSON>`: hello (protocol 1, the player's name), ping/pong every 15 s (a node quiet for 60 s is
  dropped), search/cancel, propose/accept/reject/commit/abort, sig.
- `b"ASCR" 2 <from 16> <to 16> <datagram>`: a game datagram the runtime relays.

Finding the others:

- The BitTorrent DHT (scripts/mp_dht.py, BEP 5, read-only as BEP 43 has it): every node looks up
  `SHA-1("ascension-r/multiplayer/1")` with get_peers and announces itself there (announce_peer, implied_port: the
  port its questions come from), at start, every 5 minutes, and every 30 s while its game searches; it says hello to
  every address it finds. Bootstrap: dht.libtorrent.org, dht.transmissionbt.com, router.bittorrent.com,
  router.utorrent.com, and the nodes that answered last time (`online\dht-nodes.json`), asked first.
- This PC's network: multicast to 239.255.65.82:36103 every 5 s with the node's port; the listening socket shares its
  port with the other nodes on the PC.

## Quick Play among the nodes

A node whose game searches sends the search (the game's entries, build, suggested mode and player range, its P2P
port) to every node it knows, again every 2 s; one not heard for 7 s is not counted. The players that fit together
are those with the same build (and, for a fixed-mode search, the same mode), one name once. The node with the
smallest id among them leads: our matchmaker's `pick_mode` takes the mode (a suggestion that fits, after 5 s any
known mode), for as many of them as one takes, and the leader proposes the world (16 bytes of its own, the mode, its
own player first: the host). A node that is searching and not promised elsewhere accepts; with every yes the leader
commits (three times), and each node gives its game the same WORLD_RESERVED. A no, or no answer in 2.5 s, drops the
proposal; the leader tries again a second or two later without the node that said no for 5 s. A promise not
committed in 4 s lapses. While it waits the game gets SEARCH_UPDATE with the players found.

## Signaling through the nodes

At the commit each node makes every other player of the world a `RemotePlayer` of its signaling server: found by
name, at the address it sees that player's node at and the player's P2P port. The server's messages to it
(ACTIVATED, DEACTIVATED, GONE, MOVED) go to its node as `sig`; that node hands them to its game with the address it
sees our node at in place of ours, and keeps the links (an activation, a deactivation, a player gone) as the server
would. A node only takes a player's messages from the node that player plays behind.

The runtime relays a peer's datagrams after three seconds without a direct path (phase 4): to its node's UDP port,
as with a host. For a RemotePlayer the node sends them on to the player's node, which hands them to its game's P2P
socket. Two games then reach each other wherever their nodes do. ps3recomp's signaling server got the two hooks this
needs (`relay_ready`, `relayed_from`).

## The launcher

Multiplayer has four values now: Off, Auto, Host, Join (`[online] mode = auto`). On Auto the tab says the players
are found through the BitTorrent DHT and on this network, so anyone who looks for Ascension-R players there sees
the PC's address while the game runs. "Always through the host" is "Always relayed" (the host, or the nodes).
The node and the DHT client go into the Kit outside its id (`KIT_PLAY`), as phase 5's node does.

## Runs

- tests/test_mp_dht.py: a lookup against a made-up DHT of a dozen nodes finds what another client announced, learns
  its own address, keeps the nodes that answered and starts from them.
- tests/test_mp_p2p.py: nodes on 127.0.0.1 with made-up games: one world on both, the smaller id's player the host;
  an activation and a relayed datagram crossing two nodes, GONE when a game leaves; of three players searching for a
  two-player mode the two smallest ids meet and the third waits; a game that stopped searching is left out.
- The real DHT from this PC: a client announced a test key and another socket found it (52 nodes asked, 21
  answered, 25 s). The DHT nodes see this PC's socket at a different port each: its router maps by destination.
- Two games on this PC, both on Auto through the settings: the nodes met through the multicast in four seconds, the
  second node took other ports and P2P port 3659 by itself, the one with the smaller id proposed FVS2, both games
  got the world (that node's player the host) and connected directly at the PC's network address, and the match
  started (Spa2VS). Killing the games took the nodes with them.
- The same two nodes with the multicast off: each found a dozen entries under the key (its own and the other's at
  several ports, and earlier runs'), and neither reached the other: behind a router that maps by destination and
  does not loop back, a node cannot be reached at the address the DHT holds for it.

## Still open (phase 7)

- Nodes behind routers that map by destination (this PC's) or that filter: punching between nodes coordinated
  through a node both can reach, UPnP/NAT-PMP to open the port, and relaying through a third node (or a community
  server) when nothing else gets through. Until then Auto plays on one network, and across the internet only where
  a node can be reached at its announced address.
- A beta with players on different networks; more than two players; the stats save; signing the nodes' messages.
