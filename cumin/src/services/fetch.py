import ipaddress
import socket
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_MAX_BYTES = 500_000
_MAX_CHARS = 12_000
_SKIP_TAGS = {"script", "style", "noscript"}


class FetchError(Exception):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("url must be http or https")
    _assert_public(parsed.hostname)


def fetch_page(url: str) -> str:
    assert_public_url(url)
    request = Request(url, headers={"User-Agent": "cumin-summarizer"})
    try:
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type and not content_type.startswith("text/plain"):
                raise FetchError("url did not return text")
            raw = response.read(_MAX_BYTES + 1)
    except URLError as exc:
        raise FetchError("could not fetch url") from exc
    if len(raw) > _MAX_BYTES:
        raise FetchError("page is too large")
    html = raw.decode("utf-8", errors="replace")
    if "html" not in content_type:
        text = " ".join(html.split())
    else:
        parser = _TextExtractor()
        parser.feed(html)
        text = " ".join(parser.parts)
    if not text:
        raise FetchError("page had no text")
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS]
    return text


def _assert_public(hostname: str) -> None:
    host = hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise FetchError("url host is not public")
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    try:
        addresses.append(ipaddress.ip_address(host))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise FetchError("could not resolve url host") from exc
        addresses.extend(ipaddress.ip_address(info[4][0]) for info in infos)
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise FetchError("url host is not public")
