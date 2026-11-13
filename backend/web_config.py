"""Trusted deployment configuration shared by the static exporter and HTTP server."""
import re
from urllib.parse import urlsplit


def deployment_url(value, *, origin_only=False):
    """HTTPS, or literal loopback HTTP for disposable local validation; no URL secrets."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError('invalid_deployment_url')
    url = urlsplit(value)
    # Keep the accepted spelling canonical so CSP, Origin and fetch agree exactly.
    if (not re.fullmatch(r'[a-z0-9.-]+(?::[0-9]{1,5})?', url.netloc)
            or url.username or url.password or url.query or url.fragment
            or value != url.scheme + '://' + url.netloc + url.path
            or url.scheme not in ('https', 'http')
            or (url.scheme == 'http' and url.hostname not in ('127.0.0.1', 'localhost'))):
        raise ValueError('invalid_deployment_url')
    if url.port is not None:
        # Browser URL/Origin serialization drops default ports and leading zeroes.
        # Reject those spellings before generating metadata or an Origin allowlist.
        if (not 1 <= url.port <= 65535 or str(url.port) != url.netloc.rsplit(':', 1)[1]
                or url.port == {'https': 443, 'http': 80}[url.scheme]):
            raise ValueError('invalid_deployment_url')
    prefix = url.path.rstrip('/')
    if (prefix and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', prefix)) or (origin_only and url.path):
        raise ValueError('invalid_deployment_url')
    return url.scheme + '://' + url.netloc + prefix


def ui_policy(api_base=''):
    origin = deployment_url(api_base).split('/', 3)[:3] if api_base else []
    connect = ' '.join(["'self'"] + (['/'.join(origin)] if origin else []))
    return ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src " + connect
            + "; img-src 'self'; font-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'")
