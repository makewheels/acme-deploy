class Deployer:
    def deploy(self, domain, fullchain_pem, key_pem):
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
            f"unknown DEPLOY_TARGET: {name} (available: {', '.join(sorted(_REGISTRY))})"
        )
    return _REGISTRY[name](cfg)


from . import oss_cname  # noqa: E402,F401
