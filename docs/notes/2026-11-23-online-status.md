# How many players are online, on the website (2026-11-23)

The website is static (GitHub Pages) and a browser cannot speak the BitTorrent DHT, which is UDP, so the count is
taken elsewhere and published where the page can read it, with no server of the project's own.

- `scripts/mp_status.py` looks up the key every node announces itself under (`mp_p2p.KEY`, protocol 1;
  `tests/test_mp_status.py` keeps the two the same) the way a node does, with `mp_dht.py` alone. It announces nothing
  and contacts no player. It writes `{"format", "checked", "ok", "players", "announced", "dht_nodes"}`: `players` the
  addresses announced, `announced` the address and port pairs, `ok` false when fewer than 8 DHT nodes answered (`mp_dht.K`, the closest a
  lookup ends on: fewer never got near the key, and their 0 says nothing). No address and no
  name goes into it. Its own log lines name the machine's address, so they are off unless `-v`.
- `.github/workflows/online-status.yml` runs it at minutes 7, 27 and 47 of each hour (and by hand), and puts
  `status.json` on the `status` branch as a single commit, pushed again each time. A run too few DHT nodes answered leaves
  the last count, so a passing outage neither shows zero nor fails the job.
- `site/index.html` reads `https://raw.githubusercontent.com/rigaz29/Ascension-R/status/status.json` (which GitHub
  serves to any page, cached up to 5 minutes) and says "about N players on Auto, counted M minutes ago"; older than
  three hours, or none at all, it says so. The text goes in with `textContent`. While the count is fresh, the same
  count also shows under the download buttons at the top of the page.
- The README has a badge of it: shields.io's dynamic JSON badge reads `players` from the same file
  (`cacheSeconds=600`), as a README cannot run a script.

What the count misses:

- a node behind a router that maps by destination (hard) does not announce itself, so it is not counted;
- a node announces itself every 5 minutes (every 30 s while its game searches), and the DHT keeps an announce for up
  to about 30 minutes, so a player who has just gone can still be counted;
- two players behind one router are one address;
- Host and Join games never go on the DHT.

## Runs

- `tests/test_mp_status.py` (CI): the key; on the made-up DHT of `tests/test_mp_dht.py` three nodes announce under it
  and one under another key, all from 127.0.0.1: one address, three announces; no DHT node answering: `ok` false.
- The real DHT from this PC, 2026-11-23 02:16 UTC, four hours after 0.3.0: 25 DHT nodes answered, 3 players announced.
- The first run on GitHub's machines, two minutes later: 2 DHT nodes answered, 0 players. Hence the 8 nodes a count
  now takes.
