# acme-deploy

ACME（Let's Encrypt）证书自动续期 + 可插拔部署管道。使用 DNS-01 验证，私钥不出运行环境；证书签发后自动部署到目标云服务。为定时触发的无状态环境（云函数）设计，也可以跑在任何 cron 机器上。

## 架构

```
handler / cron
   │
   ├─ renewer.acme      ACME v2 客户端（Let's Encrypt，支持 staging）
   ├─ renewer.state     状态管理（账户密钥/域名密钥/证书，可同步到 OSS）
   ├─ renewer.dns       DNS 提供商插件（DNS-01 验证用）
   │    └─ alidns        阿里云 DNS
   └─ renewer.deploy    部署目标插件
        └─ oss_cname    阿里云 OSS 自定义域名证书绑定
```

新增一个 DNS 提供商或部署目标 = 在对应目录加一个文件并 `@register("名字")`，核心流程不用动。

## 快速开始（本地）

```bash
uv sync
cp .env.example .env   # 填入真实值
uv run python handler.py
```

建议先设 `LE_STAGING=1` 测试：staging 模式走 LE 测试 CA，只签发、不部署，不会污染正式证书。

## 配置

| 变量 | 必填 | 说明 |
|---|---|---|
| `CERT_DOMAIN` | ✓ | 要签发证书的域名 |
| `LE_EMAIL` | ✓ | Let's Encrypt 账户邮箱 |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | 本地✓ | 云函数上由 RAM 角色自动注入，无需配置 |
| `ALIBABA_CLOUD_SECURITY_TOKEN` | | STS 临时凭证 token，一般不手动配 |
| `DNS_PROVIDER` | | 默认 `alidns` |
| `DEPLOY_TARGET` | | 默认 `oss_cname` |
| `OSS_BUCKET` | oss_cname ✓ | 目标 bucket |
| `OSS_REGION` | | 不填则自动探测 |
| `LE_STAGING` | | `1` = 使用 staging CA，只签发不部署 |
| `RENEW_BEFORE_DAYS` | | 剩余天数低于该值才续期，默认 `30` |
| `STATE_DIR` | | 状态目录，默认 `./state` |
| `STATE_OSS_URI` | | 如 `oss://bucket/.acme-deploy-state/`，无状态环境下持久化状态 |

## 部署到阿里云函数计算（FC）

1. 打包代码：`zip -r code.zip handler.py renewer/`
2. 依赖层（FC 是 x86_64 Linux，打包时指定平台）：
   ```bash
   uv pip install --python-platform x86_64-manylinux_2_28 --only-binary=:all: \
     --target layer/python acme cryptography dnspython josepy requests
   zip -r layer.zip layer/
   ```
3. 创建函数：Python 3.10+ runtime，上传 code.zip 和 layer.zip，入口填 `handler.handler`
4. 给函数的服务角色授权（RAM）：
   - alidns：`AddDomainRecord` / `DeleteDomainRecord` / `DescribeDomainRecords` / `GetMainDomainName`
   - oss：目标 bucket 的读写（`GetObject` / `PutObject` / cname 绑定相关权限）
   - 凭证由角色注入，函数环境变量里**不要**放 AK
5. 函数环境变量：`CERT_DOMAIN` / `LE_EMAIL` / `DNS_PROVIDER` / `DEPLOY_TARGET` / `OSS_BUCKET` / `STATE_OSS_URI`（必须，函数是无状态的）
6. 定时触发器：每天一次即可（证书剩余 30 天内才会真正续期），例如 `0 37 3 * * *`

## 扩展

新增 DNS 提供商（`renewer/dns/foo.py`）：

```python
from . import DNSProvider, register

@register("foo")
class FooDNS(DNSProvider):
    def __init__(self, cfg): ...
    def main_domain(self, domain): ...        # 返回域名的注册主域
    def add_txt(self, domain, rr, value): ... # 加 TXT 记录，返回记录句柄
    def delete_txt(self, record_id): ...      # 按句柄删除
```

新增部署目标（`renewer/deploy/bar.py`）：

```python
from . import Deployer, register

@register("bar")
class BarDeployer(Deployer):
    def __init__(self, cfg): ...
    def deploy(self, domain, fullchain_pem, key_pem): ...
```

然后在配置里设 `DNS_PROVIDER=foo` / `DEPLOY_TARGET=bar` 即可启用。

## License

MIT
