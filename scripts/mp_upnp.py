"""UPnP for the multiplayer's node (scripts/mp_p2p.py; docs/notes/2026-11-22-multiplayer-phase7.md): ask the home
router to forward the node's UDP port to this PC, as torrent clients do, so other players' nodes reach it without
anything being set up by hand.

SSDP finds an Internet Gateway Device (M-SEARCH to 239.255.255.250:1900); its description names the WANIPConnection
(or WANPPPConnection) service and its control URL; SOAP then adds the mapping (AddPortMapping, a lease the node
renews), says the router's external address (GetExternalIPAddress: a private one means another router or the ISP's
NAT is in front of it, and the mapping does not make the node reachable), and removes the mapping when the node
ends (DeletePortMapping; a node that is killed leaves it to run out). Blocking calls: the node runs them on a
thread of its own.
"""
import re
import socket
import urllib.parse
import urllib.request

SSDP = ("239.255.255.250", 1900)
SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
            "urn:schemas-upnp-org:service:WANPPPConnection:1")
PRIVATE = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|169\.254\.)")


class Error(Exception):
    pass


class Gateway:
    def __init__(self, location, service, control, local_ip):
        self.location, self.service, self.control, self.local_ip = location, service, control, local_ip

    def soap(self, action, args, timeout=5.0):
        body = "".join("<%s>%s</%s>" % (k, v, k) for k, v in args)
        env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:%s xmlns:u="%s">%s</u:%s>'
               '</s:Body></s:Envelope>' % (action, self.service, body, action))
        req = urllib.request.Request(self.control, env.encode(), {
            "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": '"%s#%s"' % (self.service, action)})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:   # urllib's errors, the router's SOAP faults (an HTTP 500), a socket that times out
            if hasattr(e, "close"):
                e.close()
            raise Error("%s: %s" % (action, e)) from None

    def external_ip(self):
        m = re.search(r"<NewExternalIPAddress>\s*([^<\s]*)\s*<", self.soap("GetExternalIPAddress", ()))
        return m.group(1) if m and m.group(1) else None

    def add(self, port, protocol="UDP", lease=3600, description="Ascension-R"):
        self.soap("AddPortMapping", (("NewRemoteHost", ""), ("NewExternalPort", port), ("NewProtocol", protocol),
                                     ("NewInternalPort", port), ("NewInternalClient", self.local_ip),
                                     ("NewEnabled", 1), ("NewPortMappingDescription", description),
                                     ("NewLeaseDuration", lease)))

    def delete(self, port, protocol="UDP"):
        self.soap("DeletePortMapping", (("NewRemoteHost", ""), ("NewExternalPort", port), ("NewProtocol", protocol)))


def local_ip_toward(host):
    """This PC's address on the way to host (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 1900))
        return s.getsockname()[0]
    finally:
        s.close()


def discover(timeout=2.0, target=SSDP):
    """The first Internet Gateway Device that answers, or None."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.settimeout(timeout)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for _ in range(2):
            s.sendto(msg, target)
        while True:
            try:
                data, addr = s.recvfrom(4096)
            except (socket.timeout, OSError):
                return None
            m = re.search(rb"(?im)^location:\s*(\S+)", data)
            if not m:
                continue
            gw = describe(m.group(1).decode("ascii", "replace"), timeout)
            if gw:
                return gw
    finally:
        s.close()


def describe(location, timeout=2.0):
    """The gateway a description names: its first WAN connection service with a control URL."""
    try:
        with urllib.request.urlopen(location, timeout=timeout) as r:
            desc = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    for service in SERVICES:
        i = desc.find("<serviceType>%s</serviceType>" % service)
        if i < 0:
            continue
        ctrl = re.search(r"<controlURL>\s*([^<\s]+)\s*</controlURL>", desc[i:])
        if not ctrl:
            continue
        host = urllib.parse.urlparse(location).hostname
        return Gateway(location, service, urllib.parse.urljoin(location, ctrl.group(1)), local_ip_toward(host))
    return None


def is_private(ip):
    return bool(ip and PRIVATE.match(ip))
