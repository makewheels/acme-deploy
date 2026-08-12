from ..oss import OssClient
from . import Deployer, register


@register("oss_cname")
class OssCnameDeployer(Deployer):
    def __init__(self, cfg):
        self.bucket = cfg.env.get("OSS_BUCKET")
        if not self.bucket:
            raise SystemExit("missing required env: OSS_BUCKET (deploy target oss_cname)")
        self.client = OssClient(
            cfg.access_key_id,
            cfg.access_key_secret,
            cfg.security_token,
            region=cfg.env.get("OSS_REGION") or None,
        )

    def deploy(self, domain, fullchain_pem, key_pem):
        self.client.resolve_region(self.bucket)
        self.client.put_bucket_cname_cert(
            self.bucket, domain, fullchain_pem.decode(), key_pem.decode()
        )
