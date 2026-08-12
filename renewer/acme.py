import datetime
import time

import dns.resolver
import josepy as jose
from acme import challenges, client as acme_client
from acme import crypto_util, errors as acme_errors, messages
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

STAGING_DIRECTORY = "https://acme-staging-v02.api.letsencrypt.org/directory"
PROD_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
USER_AGENT = "acme-deploy"


def new_ec_key_pem():
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def jwk_from_pem(pem_bytes):
    try:
        return jose.JWKEC.load(pem_bytes)
    except Exception:
        return jose.JWKRSA.load(pem_bytes)


def wait_dns_propagation(fqdn, expected_value, apex, timeout=180):
    ns_targets = [str(r.target) for r in dns.resolver.resolve(apex, "NS")]
    nameservers = []
    for target in ns_targets:
        try:
            nameservers += [str(a) for a in dns.resolver.resolve(target, "A")]
        except Exception:
            continue
    if not nameservers:
        raise RuntimeError(f"no authoritative NS found for {apex}")
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = nameservers
    resolver.lifetime = 10
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            values = {
                b"".join(r.strings).decode()
                for r in resolver.resolve(fqdn, "TXT")
            }
            if expected_value in values:
                return
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError(f"TXT {fqdn} not visible on authoritative NS after {timeout}s")


class LEClient:
    def __init__(self, account_key_pem, email, staging=False):
        jwk = jwk_from_pem(account_key_pem)
        alg = jose.ES256 if isinstance(jwk, jose.JWKEC) else jose.RS256
        self.net = acme_client.ClientNetwork(jwk, alg=alg, user_agent=USER_AGENT)
        directory_url = STAGING_DIRECTORY if staging else PROD_DIRECTORY
        directory = messages.Directory.from_json(self.net.get(directory_url).json())
        self.client = acme_client.ClientV2(directory, self.net)
        regr = messages.NewRegistration.from_data(
            email=email, terms_of_service_agreed=True
        )
        try:
            self.client.new_account(regr)
        except acme_errors.ConflictError as e:
            location = getattr(e, "location", None) or (e.args[0] if e.args else None)
            if not location:
                raise
            self.net.account = messages.RegistrationResource(uri=location)

    def obtain_certificate(self, domain, set_txt, del_txt, wait_txt, timeout=180):
        domain_key_pem = new_ec_key_pem()
        csr_pem = crypto_util.make_csr(domain_key_pem, [domain])
        orderr = self.client.new_order(csr_pem)
        handles = []
        try:
            for authz in orderr.authorizations:
                challb = next(
                    c for c in authz.body.challenges if c.typ == challenges.DNS01.typ
                )
                response, validation = challb.response_and_validation(self.net.key)
                fqdn = f"_acme-challenge.{authz.body.identifier.value}"
                handles.append(set_txt(fqdn, validation))
                wait_txt(fqdn, validation)
                self.client.answer_challenge(challb, response)
            deadline = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
            orderr = self.client.poll_and_finalize(orderr, deadline=deadline)
            return orderr.fullchain_pem.encode(), domain_key_pem
        finally:
            for h in handles:
                try:
                    del_txt(h)
                except Exception:
                    pass
