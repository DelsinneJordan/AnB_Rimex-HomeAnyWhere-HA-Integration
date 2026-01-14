"""
HomeAnywhere SOAP API Client for device discovery.

This module provides a client to interact with the HomeAnywhere cloud service
to retrieve site configuration and generate devices.yaml files automatically.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import urllib.error
import ssl


@dataclass
class FlashOutputModule:
    """Represents an IPCom output module."""
    id: int
    number: int
    type: str  # Exo8, ExoDim, ExoStore, etc.
    bus_number: int
    outputs: list[str] = field(default_factory=list)  # Output names (1-8)

    @classmethod
    def from_xml(cls, element: ET.Element) -> "FlashOutputModule":
        """Parse module from XML element."""
        outputs = []
        for i in range(1, 9):
            output_el = element.find(f"Output{i}")
            outputs.append(output_el.text if output_el is not None and output_el.text else "")

        return cls(
            id=int(element.findtext("ID", "0")),
            number=int(element.findtext("Number", "0")),
            type=element.findtext("Type", "Unknown"),
            bus_number=int(element.findtext("BusNumber", "1")),
            outputs=outputs,
        )


@dataclass
class FlashIPCom:
    """Represents an IPCom device."""
    id: int
    registration_id: str
    name: str
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    bus1: str
    bus2: str
    username: str
    password: str
    modules: list[FlashOutputModule] = field(default_factory=list)

    @classmethod
    def from_xml(cls, element: ET.Element) -> "FlashIPCom":
        """Parse IPCom from XML element."""
        modules = []
        modules_el = element.find("Modules")
        if modules_el is not None:
            for module_el in modules_el.findall("FlashOutputModule"):
                modules.append(FlashOutputModule.from_xml(module_el))

        return cls(
            id=int(element.findtext("ID", "0")),
            registration_id=element.findtext("RegistrationID", ""),
            name=element.findtext("Name", ""),
            local_address=element.findtext("LocalAddress", ""),
            local_port=int(element.findtext("LocalPort", "5000")),
            remote_address=element.findtext("RemoteAddress", ""),
            remote_port=int(element.findtext("RemotePort", "5000")),
            bus1=element.findtext("Bus1", "None"),
            bus2=element.findtext("Bus2", "None"),
            username=element.findtext("Username", ""),
            password=element.findtext("Password", ""),
            modules=modules,
        )


@dataclass
class FlashMapElement:
    """Represents a map element (device on the UI)."""
    id: int
    name: str
    type: str  # Output, Sequence, etc.
    graphic_type: str  # OutputLightBulb, OutputBlindDown, etc.
    widget_type: str  # Basic, Dimmable
    element_id: int  # IPCom ID
    element_config: str  # "bus,module,output" format

    @classmethod
    def from_xml(cls, element: ET.Element) -> "FlashMapElement":
        """Parse map element from XML."""
        return cls(
            id=int(element.findtext("ID", "0")),
            name=element.findtext("Name", ""),
            type=element.findtext("Type", ""),
            graphic_type=element.findtext("GraphicType", ""),
            widget_type=element.findtext("WidgetType", "Basic"),
            element_id=int(element.findtext("ElementID", "0")),
            element_config=element.findtext("ElementConfig", ""),
        )

    def parse_config(self) -> Optional[tuple[int, int, int]]:
        """Parse element_config into (bus, module, output) tuple."""
        if not self.element_config:
            return None
        parts = self.element_config.split(",")
        if len(parts) != 3:
            return None
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None


@dataclass
class FlashSite:
    """Represents a HomeAnywhere site."""
    id: int
    name: str
    version: str
    ipcoms: list[FlashIPCom] = field(default_factory=list)
    map_elements: list[FlashMapElement] = field(default_factory=list)

    @classmethod
    def from_login_xml(cls, element: ET.Element) -> "FlashSite":
        """Parse basic site info from login response."""
        return cls(
            id=int(element.findtext("ID", "0")),
            name=element.findtext("Name", ""),
            version=element.findtext("Version", ""),
        )


class HomeAnywhereAPI:
    """Client for HomeAnywhere SOAP API."""

    BASE_URL = "https://www.homeanywhere.net/gateway/MyLoginService.asmx"
    NAMESPACE = "http://tempuri.org/"

    def __init__(self):
        self.session_cookie: Optional[str] = None
        # Create SSL context that doesn't verify certificates (for compatibility)
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    def _build_soap_envelope(self, body_content: str) -> str:
        """Build a SOAP envelope with the given body content."""
        return f'''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
        {body_content}
    </s:Body>
</s:Envelope>'''

    def _make_request(self, soap_action: str, body: str) -> str:
        """Make a SOAP request and return the response body."""
        envelope = self._build_soap_envelope(body)

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{self.NAMESPACE}{soap_action}"',
            "Cache-Control": "no-cache, max-age=0",
        }

        if self.session_cookie:
            headers["Cookie"] = self.session_cookie

        request = urllib.request.Request(
            self.BASE_URL,
            data=envelope.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, context=self._ssl_context) as response:
                # Store session cookie if present
                set_cookie = response.headers.get("Set-Cookie")
                if set_cookie:
                    # Extract just the session ID part
                    self.session_cookie = set_cookie.split(";")[0]

                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"HTTP Error {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Connection failed: {e.reason}") from e

    def _parse_response(self, response: str, result_tag: str) -> ET.Element:
        """Parse SOAP response and extract the result element."""
        # Remove namespaces for easier parsing
        response = response.replace(' xmlns="http://tempuri.org/"', '')
        response = response.replace('xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"', '')
        response = response.replace('soap:', '')

        root = ET.fromstring(response)

        # Find the result element
        result = root.find(f".//{result_tag}")
        if result is None:
            raise ValueError(f"Could not find {result_tag} in response")

        return result

    def login(self, username: str, password: str) -> list[FlashSite]:
        """
        Login to HomeAnywhere and retrieve list of available sites.

        Args:
            username: HomeAnywhere username
            password: HomeAnywhere password

        Returns:
            List of FlashSite objects representing available sites

        Raises:
            ConnectionError: If connection fails
            ValueError: If login fails or response is invalid
        """
        body = f'''<LoginNeo xmlns="{self.NAMESPACE}">
            <username>{username}</username>
            <passwordws>{password}</passwordws>
        </LoginNeo>'''

        response = self._make_request("LoginNeo", body)
        result = self._parse_response(response, "LoginNeoResult")

        # Check if login was successful
        user_id = result.findtext("ID")
        if not user_id or user_id == "0":
            raise ValueError("Login failed: Invalid credentials")

        # Parse allowed sites
        sites = []
        allowed_sites = result.find("AllowedSites")
        if allowed_sites is not None:
            for site_el in allowed_sites.findall("FlashSite"):
                sites.append(FlashSite.from_login_xml(site_el))

        return sites

    def get_site_config(self, site_id: int, version: str) -> FlashSite:
        """
        Get full site configuration including modules and devices.

        Args:
            site_id: Site ID from login response
            version: Site version from login response

        Returns:
            FlashSite with full configuration

        Raises:
            ConnectionError: If connection fails
            ValueError: If response is invalid
        """
        body = f'''<CheckSiteVersion xmlns="{self.NAMESPACE}">
            <siteID>{site_id}</siteID>
            <version>{version}</version>
        </CheckSiteVersion>'''

        response = self._make_request("CheckSiteVersion", body)
        result = self._parse_response(response, "CheckSiteVersionResult")

        site = FlashSite(id=site_id, name="", version=version)

        # Parse IPComs
        ipcoms_el = result.find("IPComs")
        if ipcoms_el is not None:
            for ipcom_el in ipcoms_el.findall("FlashIPCom"):
                site.ipcoms.append(FlashIPCom.from_xml(ipcom_el))

        # Parse Map Elements
        maps_el = result.find("Maps")
        if maps_el is not None:
            for map_el in maps_el.findall("FlashMap"):
                elements_el = map_el.find("Elements")
                if elements_el is not None:
                    for elem_el in elements_el.findall("FlashMapElement"):
                        map_elem = FlashMapElement.from_xml(elem_el)
                        if map_elem.type == "Output":
                            site.map_elements.append(map_elem)

        return site
