import os
from pathlib import Path


def load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class Config:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.env = env
        self.domain = self._req("CERT_DOMAIN")
        self.email = self._req("LE_EMAIL")
        self.access_key_id = self._req("ALIBABA_CLOUD_ACCESS_KEY_ID")
        self.access_key_secret = self._req("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        self.security_token = env.get("ALIBABA_CLOUD_SECURITY_TOKEN") or None
        self.staging = env.get("LE_STAGING", "").lower() in ("1", "true", "yes")
        self.renew_before_days = int(env.get("RENEW_BEFORE_DAYS", "30"))
        self.state_dir = env.get("STATE_DIR", "./state")
        self.state_oss_uri = env.get("STATE_OSS_URI") or None
        self.dns_provider = env.get("DNS_PROVIDER", "alidns")
        self.deploy_target = env.get("DEPLOY_TARGET", "oss_cname")

    def _req(self, name):
        v = self.env.get(name)
        if not v:
            raise SystemExit(f"missing required env: {name}")
        return v
