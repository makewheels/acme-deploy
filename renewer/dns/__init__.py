class DNSProvider:
    def main_domain(self, domain):
        raise NotImplementedError

    def add_txt(self, domain, rr, value):
        raise NotImplementedError

    def delete_txt(self, record_id):
        raise NotImplementedError


_REGISTRY = {}


def register(name):
    def wrap(cls):
        _REGISTRY[name] = cls
        return cls
    return wrap


def create(name, cfg):
    if name not in _REGISTRY:
        raise SystemExit(
            f"unknown DNS_PROVIDER: {name} (available: {', '.join(sorted(_REGISTRY))})"
        )
    return _REGISTRY[name](cfg)


from . import alidns  # noqa: E402,F401
