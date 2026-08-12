import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509

STATE_FILES = ("account.key", "domain.key", "cert.pem")


def parse_state_oss_uri(uri):
    rest = uri.removeprefix("oss://")
    bucket, _, prefix = rest.partition("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


class State:
    def __init__(self, path):
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        return self.dir / name

    def read(self, name):
        p = self.path(name)
        return p.read_bytes() if p.exists() else None

    def write(self, name, data, private=False):
        p = self.path(name)
        p.write_bytes(data)
        if private:
            os.chmod(p, 0o600)

    def cert_days_left(self):
        pem = self.read("cert.pem")
        if not pem:
            return None
        cert = x509.load_pem_x509_certificate(pem)
        delta = cert.not_valid_after_utc - datetime.now(timezone.utc)
        return delta.days

    def sync_from_oss(self, oss, bucket, prefix):
        for name in STATE_FILES:
            data = oss.get_object(bucket, prefix + name)
            if data is not None:
                self.write(name, data, private=name.endswith(".key"))

    def sync_to_oss(self, oss, bucket, prefix):
        for name in STATE_FILES:
            data = self.read(name)
            if data is not None:
                oss.put_object(bucket, prefix + name, data)
