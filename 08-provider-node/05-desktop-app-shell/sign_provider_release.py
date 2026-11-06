"""Create signed update metadata on an offline release machine. Does not publish."""
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import re
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=Path, required=True, help="Encrypted Ed25519 PEM outside the checkout")
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--minimum-version", required=True)
    parser.add_argument("--channel", choices=("stable", "testing"), required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    if args.key.resolve().is_relative_to(repo):
        parser.error("Keep the private signing key outside the checkout")
    if args.installer.name != "ComputeTorrent-Provider-Setup.exe":
        parser.error("Select the approved Windows setup executable")
    pattern = r"[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,2}-update[0-9]{1,9}"
    if any(not re.fullmatch(pattern, v) for v in (args.version, args.minimum_version)):
        parser.error("Unsupported provider build version")
    size = args.installer.stat().st_size
    if not 0 < size <= 512 * 1024 * 1024 or not 0 < args.sequence < 2**63:
        parser.error("Invalid release size or sequence")

    password = getpass.getpass("Signing key password: ").encode()
    if not password:
        parser.error("An encrypted signing key is required")
    key = serialization.load_pem_private_key(args.key.read_bytes(), password)
    if not isinstance(key, Ed25519PrivateKey):
        parser.error("An Ed25519 signing key is required")
    digest = hashlib.sha256()
    with args.installer.open("rb") as source:
        while chunk := source.read(512 * 1024):
            digest.update(chunk)
    now = int(time.time())
    release = dict(schema=1, channel=args.channel, platform="windows-x64",
                   filename=args.installer.name, version=args.version,
                   minimum_version=args.minimum_version, sequence=args.sequence,
                   issued=now, expires=now + 7 * 86400, size=size, sha256=digest.hexdigest())
    message = json.dumps(release, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    signature = base64.b64encode(key.sign(message)).decode()
    with args.output.open("x", encoding="utf-8") as output:
        json.dump({"release": release, "signature": signature}, output)


if __name__ == "__main__":
    main()
