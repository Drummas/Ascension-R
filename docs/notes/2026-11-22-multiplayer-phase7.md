# Multiplayer phase 7: nodes through routers

Phase 6 (2026-11-22-multiplayer-phase6.md) let players' nodes find each other with no host, but a node behind a
router is not reached at the address the DHT holds for it: on this PC's network the nodes met only by multicast.
Phase 7 gets them through: the router is asked to forward the node's port, nodes that know each other introduce the
ones that do not and those punch through, and when nothing gets through a third node carries their messages and
their games' datagrams. Anyone can run a node with no game on a reachable machine (a community node) to introduce and
carry for the others.

## How a node is reached

- UPnP (scripts/mp_upnp.py): SSDP finds the router's Internet Gateway Device, its description the WANIPConnection
  (or WANPPPConnection) control URL; AddPortMapping forwards the node's UDP port for an hour, renewed every half
  hour, and DeletePortMapping takes it away when the node closes (a node that is killed leaves it to run out).
  GetExternalIPAddress says whether that makes the node reachable: a private address means another router or the
  ISP's NAT is in front. A public one that is also the address the DHT sees: the node gives out that address and
  the forwarded port as they are (`fwd` in hello and in `peers`, first in a `punch`, and announced on the DHT with
  implied_port 0), since a router may still send the node's own packets out from other ports (one that maps by
  destination does), and those are no way in. A renewal the router refuses takes it back.
- What the node says of itself (`nat` in hello): open (a forwarded port whose router has the address the DHT sees, or
  a community node), easy (every DHT node saw it at one port: a router that maps by source), hard (another port for
  each: a router that maps by destination), ? (not known yet). A hard node no longer announces itself on the DHT
  (nobody would reach it there); it still looks the others up.

## Introductions and punching

Every 20 s a node tells each node it talks to directly which nodes it knows (`peers`: id, name, nat, the address it
sees each at, their own network's addresses). A node that hears of one it does not reach says hello to that address
(it may be open) and asks the node that told it for an introduction (`intro`, once a minute; once in ten minutes for
one it already reaches through another). The introducer sends both `punch` with the other's addresses, and both say
hello to them every 0.25 s for 4 s: two routers that map by source let the crossed hellos through. While its game
searches, a node also says hello again every 5 s to the addresses its last DHT lookup found.

| A | B | |
|---|---|---|
| open | any | direct |
| easy | easy | direct after the punch |
| hard | easy | direct only when B's router lets in any port of an address it sent to; else carried |
| hard | hard | carried |

## Carrying

When the punch gets nothing through, the two nodes talk through the node that introduced them: a message for the
other goes to it as `fwd` (to, the message), and it hands it on as `fwded` (from, the message); a game datagram the
runtime relays goes as kind 3 (to: 8 bytes, the packet) and comes out as kind 4 (from: 8 bytes, the packet). A node
carries for 8 pairs at most and only between nodes it reaches itself; "Help others connect" off carries for none.
Quick Play, signaling and the games' datagrams then work as between any two nodes. A direct hello from a node
reached through another makes the path direct again.

## The settings

`[online]` for Auto: `upnp` (off), `relay_others` (off), `nodes` (community nodes, host[:port] with a comma between, port
36102 when left out), and for tests `lan` and `dht` (on). The launcher's Multiplayer tab has Open the port on the
router, Help others connect and Community nodes. `GOWA_MP_DIRECT=0` (tests) keeps a node from reaching any node but
the named ones itself.

A community node: `python scripts/mp_p2p.py community [--port 36102] [--no-dht] [--lan] [--upnp]` on a machine
players can reach (its UDP port forwarded, or a server): on the DHT as an open node, it introduces the nodes that
reach it and carries for the ones that cannot reach each other.

## Runs

- tests/test_mp_upnp.py: a made-up gateway (SSDP, description, SOAP): discovery, a mapping in with this PC's address
  and out again, the external address, a router's fault.
- tests/test_mp_nat.py: made-up routers in front of two nodes, a third node with none. Behind cone routers the two
  are introduced and punch through to each other; behind symmetric ones nothing gets through and after 4 s they talk
  through the third node, where Quick Play gives both the same world and a relayed game datagram goes through it;
  a node carries for 8 pairs at most. One of the two behind a symmetric router that also forwards it a port: when
  the node gives that port out, the other reaches it there and the two talk directly; when it does not, they are
  carried by the third. tests/test_mp_dht.py: a port announced as it is (implied_port 0). tests/test_mp_upnp.py:
  open and the port given out only when the router's address outside is the one the DHT sees.
- This PC: no UPnP gateway answers, and its router maps by destination (hard): other players cannot reach it, it
  reaches the open ones.
- Two games on this PC on Auto, LAN and DHT off, a community node on this PC named in both settings,
  `GOWA_MP_DIRECT=0` and Always relayed on: each node reached only the community node, was introduced to the other,
  punched, got nothing through, and talked to it through the community node; the nodes agreed on an FVS2 world, the
  games' signaling and every datagram went game, node, community node, node, game, and the match ran (Spa2VS).

## The beta

What is left can only be tried with players on other networks: a pre-release with Auto, a few players at home and on
mobile data, and a community node on a reachable machine (a cheap or free server, or a player's PC with UPnP). From
each: whether they met, whether the match ran, and the report (it adds multiplayer-node.log, every address hidden).

## Still open

- NAT-PMP/PCP beside UPnP, IPv6 between nodes that have it.
- Messages are not signed: a node can claim another's id. Limits on what one node sends.
- More than two players, the stats save after a match.
