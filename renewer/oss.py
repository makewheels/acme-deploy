import base64
import hashlib
import hmac
import re
from email.utils import formatdate

import requests


class OssClient:
    def __init__(self, access_key_id, access_key_secret, security_token=None, region=None):
        self.ak = access_key_id
        self.sk = access_key_secret
        self.token = security_token
        self.region = region
        self.session = requests.Session()

    def _host(self, bucket):
        return f"{bucket}.oss-{self.region}.aliyuncs.com"

    def _request(self, method, bucket, key="", sub=(), data=None, headers=None):
        headers = dict(headers or {})
        headers["Date"] = formatdate(usegmt=True)
        if self.token:
            headers["x-oss-security-token"] = self.token
        if data is not None:
            headers.setdefault("Content-Type", "application/octet-stream")
            headers["Content-MD5"] = base64.b64encode(hashlib.md5(data).digest()).decode()
        canon_oss = "".join(
            f"{k.lower()}:{v.strip()}\n"
            for k, v in sorted(headers.items())
            if k.lower().startswith("x-oss-")
        )
        resource = f"/{bucket}/{key}"
        if sub:
            resource += "?" + "&".join(sorted(sub))
        to_sign = (
            f"{method}\n"
            f"{headers.get('Content-MD5', '')}\n"
            f"{headers.get('Content-Type', '')}\n"
            f"{headers['Date']}\n"
            f"{canon_oss}{resource}"
        )
        headers["Authorization"] = "OSS " + self.ak + ":" + base64.b64encode(
            hmac.new(self.sk.encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        url = f"https://{self._host(bucket)}/{key}"
        if sub:
            url += "?" + "&".join(sorted(sub))
        r = self.session.request(method, url, data=data, headers=headers, timeout=60)
        if r.status_code >= 300:
            raise RuntimeError(f"oss {method} {resource}: HTTP {r.status_code} {r.text[:500]}")
        return r

    def resolve_region(self, bucket):
        if self.region:
            return self.region
        self.region = "cn-hangzhou"
        r = self._request("GET", bucket, sub=("location",))
        m = re.search(rb"<LocationConstraint>([^<]+)</LocationConstraint>", r.content)
        if not m:
            raise RuntimeError(f"cannot parse bucket location: {r.text[:200]}")
        self.region = m.group(1).decode().removeprefix("oss-")
        return self.region

    def put_bucket_cname_cert(self, bucket, domain, cert_pem, key_pem):
        body = (
            "<BucketCnameConfiguration><Cname>"
            f"<Domain>{domain}</Domain>"
            "<CertificateConfiguration>"
            f"<Certificate>{cert_pem}</Certificate>"
            f"<PrivateKey>{key_pem}</PrivateKey>"
            "<Force>true</Force>"
            "</CertificateConfiguration>"
            "</Cname></BucketCnameConfiguration>"
        ).encode()
        self._request(
            "POST", bucket, sub=("cname", "comp=add"), data=body,
            headers={"Content-Type": "application/xml"},
        )

    def get_object(self, bucket, key):
        r = self.session.get(
            f"https://{self._host(bucket)}/{key}",
            headers=self._auth_headers("GET", bucket, key),
            timeout=60,
        )
        if r.status_code == 404:
            return None
        if r.status_code >= 300:
            raise RuntimeError(f"oss GET {key}: HTTP {r.status_code}")
        return r.content

    def put_object(self, bucket, key, data):
        self._request("PUT", bucket, key=key, data=data)

    def _auth_headers(self, method, bucket, key):
        headers = {"Date": formatdate(usegmt=True)}
        if self.token:
            headers["x-oss-security-token"] = self.token
        canon_oss = "".join(
            f"{k.lower()}:{v.strip()}\n"
            for k, v in sorted(headers.items())
            if k.lower().startswith("x-oss-")
        )
        to_sign = f"{method}\n\n\n{headers['Date']}\n{canon_oss}/{bucket}/{key}"
        headers["Authorization"] = "OSS " + self.ak + ":" + base64.b64encode(
            hmac.new(self.sk.encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        return headers
