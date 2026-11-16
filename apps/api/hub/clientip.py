"""The caller's IP address, recorded on audit rows and sessions.

The API sits behind the web container's proxy, so the socket peer is the proxy. The real client address is the
entry the trusted proxy appended to X-Forwarded-For: counted from the right (TRUSTED_PROXY_HOPS, default 1), never the
left-most value, which a client can forge. The header is ignored unless the direct peer is a private/loopback address.
"""
import ipaddress
import os
from contextvars import ContextVar

current_ip: ContextVar[str] = ContextVar('current_ip', default='')


def _valid(value):
    try:
        addr = ipaddress.ip_address(value.strip().strip('[]'))
        return str(getattr(addr, 'ipv4_mapped', None) or addr)
    except ValueError:
        return ''


def client_ip(headers, peer=''):
    peer_ip = _valid(peer or '')
    trusted = False
    if peer_ip:
        addr = ipaddress.ip_address(peer_ip)
        trusted = addr.is_private or addr.is_loopback
    if trusted:
        parts = [p for p in (headers.get('x-forwarded-for') or '').split(',') if p.strip()]
        hops = max(1, int(os.getenv('TRUSTED_PROXY_HOPS', '1') or 1))
        if len(parts) >= hops and _valid(parts[-hops]):
            return _valid(parts[-hops])
        real = _valid(headers.get('x-real-ip') or '')
        if real:
            return real
    return peer_ip


def ip_default():
    return current_ip.get()
