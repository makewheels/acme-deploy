import base64
import hashlib
import hmac
import time
import uuid
import urllib.parse

import requests

from . import DNSProvider, register

API = "https://alidns.aliyuncs.com/"
VERSION = "2015-01-09"


@register("alidns")
class AliDNS(DNSProvider):
    def __init__(self, cfg):
        self.ak = cfg.access_key_id
        self.sk = cfg.access_key_secret
        self.token = cfg.security_token
        self.session = requests.Session()

    def _call(self, action, **params):
        p = {
            "Action": action,
            "Version": VERSION,
            "Format": "JSON",
            "AccessKeyId": self.ak,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "SignatureVersion": "1.0",
            "SignatureNonce": uuid.uuid4().hex,
        }
        if self.token:
            p["SecurityToken"] = self.token
        p.update(params)
        enc = lambda s: urllib.parse.quote(str(s), safe="~")
        canonical = "&".join(f"{enc(k)}={enc(p[k])}" for k in sorted(p))
        to_sign = "GET&%2F&" + enc(canonical)
        sig = base64.b64encode(
            hmac.new((self.sk + "&").encode(), to_sign.encode(), hashlib.sha1).digest()
        ).decode()
        r = self.session.get(API, params={**p, "Signature": sig}, timeout=30)
        data = r.json()
        if r.status_code >= 400 or "Code" in data:
            raise RuntimeError(f"alidns {action} failed: HTTP {r.status_code} {data}")
        return data

    def main_domain(self, domain):
        return self._call("GetMainDomainName", InputString=domain)["DomainName"]

    def add_txt(self, domain, rr, value):
        return self._call(
            "AddDomainRecord", DomainName=domain, RR=rr, Type="TXT", Value=value
        )["RecordId"]

    def find_txt(self, domain, rr):
        data = self._call(
            "DescribeDomainRecords",
            DomainName=domain,
            RRKeyWord=rr,
            TypeKeyWord="TXT",
            PageSize=500,
        )
        return [
            r
            for r in data.get("DomainRecords", {}).get("Record", [])
            if r["RR"] == rr and r["Type"] == "TXT"
        ]

    def delete_txt(self, record_id):
        self._call("DeleteDomainRecord", RecordId=record_id)
