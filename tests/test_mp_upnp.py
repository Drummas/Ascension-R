#!/usr/bin/env python3
"""scripts/mp_upnp.py, the node's UPnP (docs/notes/2026-11-22-multiplayer-phase7.md).

A made-up gateway on 127.0.0.1: an SSDP answer naming its description, the description with a WANIPConnection
service, and SOAP for AddPortMapping, GetExternalIPAddress and DeletePortMapping. discover finds it, a mapping goes
in with this PC's address and comes out again, the external address is read, a router's fault is an Error, and a
private external address says another NAT is in front.

Usage:
    python tests/test_mp_upnp.py
"""
import http.server
import re
import socket
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mp_upnp  # noqa: E402

DESC = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType><deviceList><device><deviceList><device>
<serviceList><service><serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
<controlURL>/ctl/IPConn</controlURL></service></serviceList></device></deviceList></device></deviceList></device></root>"""


class Gateway:
    def __init__(self, external="11.22.33.44"):
        self.external, self.mappings, self.fail = external, {}, False
        gw = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.reply(200, DESC)

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                action = self.headers["SOAPAction"].strip('"').split("#")[1]
                arg = dict(re.findall(r"<(New\w+)>([^<]*)</New\w+>", body))
                if gw.fail:
                    self.reply(500, "<s:Fault>ConflictInMappingEntry</s:Fault>")
                elif action == "AddPortMapping":
                    gw.mappings[(arg["NewExternalPort"], arg["NewProtocol"])] = (arg["NewInternalClient"],
                                                                                 arg["NewLeaseDuration"])
                    self.reply(200, "<u:AddPortMappingResponse/>")
                elif action == "DeletePortMapping":
                    gw.mappings.pop((arg["NewExternalPort"], arg["NewProtocol"]), None)
                    self.reply(200, "<u:DeletePortMappingResponse/>")
                elif action == "GetExternalIPAddress":
                    self.reply(200, "<u:R><NewExternalIPAddress>%s</NewExternalIPAddress></u:R>" % gw.external)
                else:
                    self.reply(500, "<s:Fault>Invalid Action</s:Fault>")

            def reply(self, code, text):
                data = text.encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.ssdp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ssdp.bind(("127.0.0.1", 0))
        self.ssdp.settimeout(0.2)
        self.stopping = False
        threading.Thread(target=self.answer, daemon=True).start()

    def answer(self):
        while not self.stopping:
            try:
                data, addr = self.ssdp.recvfrom(2048)
            except (socket.timeout, OSError):
                continue
            if data.startswith(b"M-SEARCH"):
                self.ssdp.sendto(b"HTTP/1.1 200 OK\r\nLOCATION: http://127.0.0.1:%d/rootDesc.xml\r\n\r\n" %
                                 self.http.server_port, addr)

    def stop(self):
        self.stopping = True
        self.http.shutdown()
        self.http.server_close()
        self.ssdp.close()


class Upnp(unittest.TestCase):
    def setUp(self):
        self.gw = Gateway()
        self.addCleanup(self.gw.stop)

    def find(self):
        g = mp_upnp.discover(timeout=2, target=("127.0.0.1", self.gw.ssdp.getsockname()[1]))
        self.assertIsNotNone(g)
        return g

    def test_a_mapping_in_and_out(self):
        g = self.find()
        self.assertEqual(g.service, "urn:schemas-upnp-org:service:WANIPConnection:1")
        self.assertTrue(g.control.endswith("/ctl/IPConn"))
        g.add(36102, lease=3600)
        self.assertEqual(self.gw.mappings[("36102", "UDP")], ("127.0.0.1", "3600"))
        self.assertEqual(g.external_ip(), "11.22.33.44")
        g.delete(36102)
        self.assertEqual(self.gw.mappings, {})

    def test_a_routers_fault(self):
        g = self.find()
        self.gw.fail = True
        with self.assertRaises(mp_upnp.Error):
            g.add(36102)

    def test_nobody_answers(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        self.addCleanup(s.close)
        self.assertIsNone(mp_upnp.discover(timeout=0.5, target=("127.0.0.1", s.getsockname()[1])))

    def test_private_external_addresses(self):
        for ip in ("10.1.2.3", "192.168.0.1", "172.20.0.1", "100.64.1.1", "169.254.3.4"):
            self.assertTrue(mp_upnp.is_private(ip), ip)
        for ip in ("11.22.33.44", "172.32.0.1", "100.128.0.1", None, ""):
            self.assertFalse(mp_upnp.is_private(ip), ip)


if __name__ == "__main__":
    unittest.main()
