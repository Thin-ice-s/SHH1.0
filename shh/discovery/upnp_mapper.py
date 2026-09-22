"""
SHH 1.0 - Router UPnP / NAT-PMP Auto Port Forwarder
Enables zero-configuration port forwarding through home routers/gateways.
"""

import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple


class UPnPMapper:
    SSDP_ADDR = "239.255.255.250"
    SSDP_PORT = 1900
    SSDP_MX = 2

    SSDP_DISCOVERY = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 2\r\n"
        "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
        "\r\n"
    )

    def __init__(self):
        self.control_url: Optional[str] = None
        self.service_type: Optional[str] = None
        self.external_ip: Optional[str] = None
        self.mapped_ports: Dict[int, int] = {}  # internal_port -> external_port

    def discover_gateway(self, timeout: float = 2.0) -> bool:
        """Discover UPnP-enabled Internet Gateway Device on the local network."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        location_url = None
        try:
            sock.sendto(self.SSDP_DISCOVERY.encode("utf-8"), (self.SSDP_ADDR, self.SSDP_PORT))
            while True:
                data, _ = sock.recvfrom(4096)
                res = data.decode("utf-8", errors="ignore")
                match = re.search(r"LOCATION:\s*(http://[^\r\n]+)", res, re.IGNORECASE)
                if match:
                    location_url = match.group(1).strip()
                    break
        except socket.timeout:
            pass
        except Exception:
            pass
        finally:
            sock.close()

        if not location_url:
            return False

        # Parse IGD Device Description XML
        try:
            req = urllib.request.Request(location_url, headers={"User-Agent": "SHH-UPnP/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                xml_data = resp.read()

            root = ET.fromstring(xml_data)
            # Find WANIPConnection or WANPPPConnection service
            ns = {"ns": "urn:schemas-upnp-org:device-1-0"}
            for service in root.findall(".//{urn:schemas-upnp-org:device-1-0}service"):
                st_el = service.find("{urn:schemas-upnp-org:device-1-0}serviceType")
                ctrl_el = service.find("{urn:schemas-upnp-org:device-1-0}controlURL")
                if st_el is not None and ctrl_el is not None:
                    st_text = st_el.text or ""
                    if "WANIPConnection" in st_text or "WANPPPConnection" in st_text:
                        self.service_type = st_text
                        self.control_url = urllib.parse.urljoin(location_url, ctrl_el.text)
                        return True
        except Exception:
            return False
        return False

    def add_port_mapping(
        self,
        internal_port: int,
        external_port: int,
        protocol: str = "TCP",
        description: str = "SHH AI Bridge",
        local_ip: Optional[str] = None
    ) -> bool:
        """Request the router to forward external_port -> internal_port on local_ip."""
        if not self.control_url or not self.service_type:
            if not self.discover_gateway():
                return False

        if not local_ip:
            # Detect local LAN IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "127.0.0.1"

        soap_body = f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:AddPortMapping xmlns:u="{self.service_type}">
      <NewRemoteHost></NewRemoteHost>
      <NewExternalPort>{external_port}</NewExternalPort>
      <NewProtocol>{protocol.upper()}</NewProtocol>
      <NewInternalPort>{internal_port}</NewInternalPort>
      <NewInternalClient>{local_ip}</NewInternalClient>
      <NewEnabled>1</NewEnabled>
      <NewPortMappingDescription>{description}</NewPortMappingDescription>
      <NewLeaseDuration>0</NewLeaseDuration>
    </u:AddPortMapping>
  </s:Body>
</s:Envelope>"""

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{self.service_type}#AddPortMapping"',
            "User-Agent": "SHH-UPnP/1.0"
        }

        try:
            req = urllib.request.Request(self.control_url, data=soap_body.encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status in (200, 204):
                    self.mapped_ports[internal_port] = external_port
                    return True
        except Exception:
            return False
        return False

    def delete_port_mapping(self, external_port: int, protocol: str = "TCP") -> bool:
        """Remove a port mapping from the router."""
        if not self.control_url or not self.service_type:
            return False

        soap_body = f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:DeletePortMapping xmlns:u="{self.service_type}">
      <NewRemoteHost></NewRemoteHost>
      <NewExternalPort>{external_port}</NewExternalPort>
      <NewProtocol>{protocol.upper()}</NewProtocol>
    </u:DeletePortMapping>
  </s:Body>
</s:Envelope>"""

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{self.service_type}#DeletePortMapping"',
            "User-Agent": "SHH-UPnP/1.0"
        }

        try:
            req = urllib.request.Request(self.control_url, data=soap_body.encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False
