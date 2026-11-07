"""Bounded operator-authorized coordinator candidates and domain-separated proofs."""
import hashlib
import hmac
import ipaddress
import json
import secrets
import urllib.request
from urllib.parse import urlsplit, urlunsplit


def endpoint(value):
    p = urlsplit(value)
    if (p.scheme not in {"ws", "wss"} or not p.hostname or p.username is not None
            or p.path != "/ws/seeder" or p.query or p.fragment or p.port == 0):
        raise ValueError("Invalid coordinator candidate")
    if p.scheme == "ws" and p.hostname != "localhost":
        address = ipaddress.ip_address(p.hostname)
        ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7")
        if not any(address in ipaddress.ip_network(net) for net in ranges):
            raise ValueError("Internet coordinator candidates require WSS")
    return value


def candidates(values):
    if not isinstance(values, list) or len(values) > 4:
        raise ValueError("At most four operator coordinator endpoints are supported")
    return list(dict.fromkeys(endpoint(v) for v in values))


def proof(key_hash, domain, *parts):
    return hmac.new(key_hash.encode(), (domain + "|" + "|".join(parts)).encode(), hashlib.sha256).hexdigest()


def register_digest(message):
    value = {k: message[k] for k in ("node_id", "tier", "profile")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def select_endpoint(primary, alternatives, node_id, token, probe=None):
    """Reprobe on each reconnect. No credential is sent to a candidate endpoint."""
    key = hashlib.sha256(token.encode()).hexdigest()
    def network_probe(url, nonce):
        p = urlsplit(url)
        target = urlunsplit(("https" if p.scheme == "wss" else "http", p.netloc, "/api/network/identity", "", ""))
        body = json.dumps(dict(node_id=node_id, nonce=nonce, endpoint=url)).encode()
        request = urllib.request.Request(target, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=2) as response:
            raw = response.read(4097)
        if len(raw) > 4096:
            raise ValueError("Candidate response too large")
        return json.loads(raw)
    probe = probe or network_probe
    validated = candidates(alternatives)
    # A TLS public endpoint remains usable when LAN disappears. Only candidates
    # received from the enrolled coordinator can precede the operator primary.
    ordered = sorted(validated, key=lambda u: urlsplit(u).scheme != "ws")
    for url in ordered:
        nonce = secrets.token_hex(32)
        try:
            response = probe(url, nonce)
            expected = proof(key, "ct-endpoint-v1", nonce, url)
            if isinstance(response, dict) and hmac.compare_digest(response.get("proof", ""), expected):
                return url
        except Exception:
            continue
    return primary
