import logging

from renewer import acme
from renewer import deploy as deployers
from renewer import dns as dns_providers
from renewer.config import Config, load_dotenv
from renewer.oss import OssClient
from renewer.state import State, parse_state_oss_uri

log = logging.getLogger("acme-deploy")


def run():
    load_dotenv()
    cfg = Config()
    dns = dns_providers.create(cfg.dns_provider, cfg)
    target = deployers.create(cfg.deploy_target, cfg)
    st = State(cfg.state_dir)

    sync = None
    if cfg.state_oss_uri:
        sb, sp = parse_state_oss_uri(cfg.state_oss_uri)
        oss = OssClient(cfg.access_key_id, cfg.access_key_secret, cfg.security_token)
        oss.resolve_region(sb)
        st.sync_from_oss(oss, sb, sp)
        sync = lambda: st.sync_to_oss(oss, sb, sp)
        log.info("state synced from %s", cfg.state_oss_uri)

    days_left = st.cert_days_left()
    if days_left is not None and days_left > cfg.renew_before_days:
        log.info("cert for %s has %d days left (> %d), skip",
                 cfg.domain, days_left, cfg.renew_before_days)
        return

    account_pem = st.read("account.key")
    if not account_pem:
        account_pem = acme.new_ec_key_pem()
        st.write("account.key", account_pem, private=True)

    apex = dns.main_domain(cfg.domain)

    def set_txt(fqdn, value):
        rr = fqdn[: -len(apex)].rstrip(".")
        rid = dns.add_txt(apex, rr, value)
        log.info("TXT added: %s (%s)", fqdn, rid)
        return rid

    def del_txt(rid):
        dns.delete_txt(rid)
        log.info("TXT deleted: %s", rid)

    def wait_txt(fqdn, value):
        log.info("waiting DNS propagation for %s", fqdn)
        acme.wait_dns_propagation(fqdn, value, apex)

    le = acme.LEClient(account_pem, cfg.email, staging=cfg.staging)
    fullchain_pem, domain_key_pem = le.obtain_certificate(
        cfg.domain, set_txt, del_txt, wait_txt
    )
    st.write("cert.pem", fullchain_pem)
    st.write("domain.key", domain_key_pem, private=True)
    log.info("certificate issued for %s (staging=%s)", cfg.domain, cfg.staging)

    if cfg.staging:
        log.info("staging mode: skip deploy")
    else:
        target.deploy(cfg.domain, fullchain_pem, domain_key_pem)
        log.info("cert deployed to %s via %s", cfg.domain, cfg.deploy_target)

    if sync:
        sync()
        log.info("state synced to %s", cfg.state_oss_uri)


def handler(event, context):
    run()
    return "ok"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
