from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

from app.models.llm_models import LLMProviderType

_LOCAL_PROVIDERS: set[LLMProviderType] = {
    LLMProviderType.ollama,
    LLMProviderType.lmstudio,
    LLMProviderType.custom,
    LLMProviderType.llamafile,
}

_ALLOW_PRIVATE = os.environ.get("FOLIO_ENRICH_ALLOW_PRIVATE_URLS", "").lower() in (
    "1",
    "true",
    "yes",
)


def _is_private_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return False


def validate_base_url(url: str, provider_type: LLMProviderType) -> str:
    """Validate a base URL for SSRF safety.

    - Cloud providers require HTTPS (unless ALLOW_PRIVATE_URLS is set).
    - Local providers (ollama, lmstudio, custom, llamafile) allow HTTP.
    - Cloud providers block private/reserved IPs unless ALLOW_PRIVATE_URLS is set.

    Returns the validated URL or raises ValueError.
    """
    parsed = urlparse(url)

    if not parsed.scheme:
        raise ValueError(f"URL must include a scheme (http:// or https://): {url}")

    if not parsed.hostname:
        raise ValueError(f"URL must include a hostname: {url}")

    is_local = provider_type in _LOCAL_PROVIDERS

    # Cloud providers require HTTPS
    if not is_local and not _ALLOW_PRIVATE and parsed.scheme != "https":
        raise ValueError(
            f"Cloud provider {provider_type.value} requires HTTPS. Got: {parsed.scheme}"
        )

    # Resolve hostname and check for private IPs (cloud providers only)
    if not is_local and not _ALLOW_PRIVATE:
        try:
            results = socket.getaddrinfo(
                parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP
            )
            for _family, _type, _proto, _canonname, sockaddr in results:
                addr = sockaddr[0]
                if _is_private_ip(addr):
                    raise ValueError(
                        f"Cloud provider URL resolves to private IP ({addr}). "
                        f"Set FOLIO_ENRICH_ALLOW_PRIVATE_URLS=true to allow."
                    )
        except socket.gaierror:
            raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")

    return url
