"""Collect independently verified HTTPS certificates for the Pages build."""

import base64
import hashlib
import json
import socket
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HOSTS = ("chatgpt.com",)
OUTPUT = Path("_site/api/tls-baselines.json")


def collect(host, context):
    with socket.create_connection((host, 443), timeout=10) as connection:
        with context.wrap_socket(connection, server_hostname=host) as tls:
            certificate = tls.getpeercert(binary_form=True)
    public_key = subprocess.run(
        ["openssl", "x509", "-inform", "DER", "-pubkey", "-noout"],
        input=certificate, capture_output=True, check=True,
    ).stdout.decode("ascii")
    spki = base64.b64decode("".join(public_key.splitlines()[1:-1]), validate=True)
    return {
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "certificateSha256": hashlib.sha256(certificate).hexdigest(),
        "spkiSha256": hashlib.sha256(spki).hexdigest(),
    }


def main():
    context = ssl.create_default_context()
    baselines = {host: collect(host, context) for host in HOSTS}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"version": 1, "hosts": baselines}, indent=2) + "\n")


if __name__ == "__main__":
    main()
