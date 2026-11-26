# Chrome 证书信任设置与自签名证书导入

在 macOS 版 Chrome 中，可以使用 **Chrome Root Store** 验证公网站点，并在指定的 **Chrome 个人资料**中单独信任经过核对的内网站点证书。下面以本机回环地址 `127.0.0.1` 为例。 [Chrome Root Store 常见问题](https://chromium.googlesource.com/chromium/src/+/main/net/data/ssl/chrome_root_store/faq.md)

## 限制 Chrome 的证书信任来源

1. 在要配置的 Chrome 个人资料里打开 `chrome://certificate-manager/localcerts`。在 macOS 区域关闭 **「使用从操作系统导入的本地证书」**（Use imported local certificates from your operating system）。Chrome 的公开根证书可在 `chrome://certificate-manager/crscerts` 查看。 [Chromium 证书管理器](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/resources/certificate_manager/local_certs_section.html.ts)
2. 打开 `chrome://certificate-manager/localcerts/usercerts`，核对 **「受信任的证书」** 中已经手动导入的条目，只保留你确认需要的证书。如果有 **「由管理员安装」**，也要核对其中的信任项，Chrome 管理策略可以单独下发证书。 [Chromium 证书信任配置](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/net/profile_network_context_service.cc)

如果系统证书开关是灰色的，在 `chrome://policy` 查找 **`CAPlatformIntegrationEnabled`**。`true` 表示启用系统证书集成，`false` 表示关闭。「未设置」表示企业策略没有指定该值，Chrome 的默认值为启用。可以手动修改的版本以证书管理器显示的开关状态为准。受管环境可通过 Chrome 的 macOS 配置描述文件下发布尔值 `false`，再到 `chrome://policy` 核实。 [Chromium 策略定义](https://chromium.googlesource.com/chromium/src/+/HEAD/components/policy/resources/templates/policy_definitions/CertificateManagement/CAPlatformIntegrationEnabled.yaml) · [Chrome 企业版 macOS 策略配置](https://support.google.com/chrome/a/answer/9020077)

## 导入自签名站点证书

1. **取得服务端当前使用的单张站点证书。** 从服务器取 `server.crt`，或在 Chrome DevTools 的 **「隐私和安全 → 概览 → 查看证书」** 中打开证书查看器，在 **「详细信息」** 选中站点证书并导出。导入前，用服务端原件或管理员从可信渠道提供的 **SHA-256 指纹**独立核对。**`server.key` 是 TLS 私钥，应留在服务器上。** [Chrome DevTools](https://developer.chrome.com/docs/devtools/security/) · [MDN TLS 服务器身份验证](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Transport_Layer_Security#server_authentication)
2. **核对访问地址和有效期。** 直接用 IP 访问时，证书的 SAN 需包含类型为 IP 地址的 `127.0.0.1`，并且当前时间须在证书的有效期内。 [RFC 9110 的 HTTPS IP 地址匹配规则](https://www.rfc-editor.org/rfc/rfc9110.html#section-4.3.5)
3. **在 Chrome 中导入。** 按 `⌘L`，粘贴 `chrome://certificate-manager/localcerts/usercerts` 后回车。在 **「受信任的证书」** 旁点 **「导入」**，选择 `.crt`、`.cer` 或只包含一张证书的 `.pem`。如果之前只在 macOS 钥匙串里设了信任，关闭系统证书集成后也要通过这里添加。 [Chromium 证书管理器路由](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/resources/certificate_manager/navigation.ts) · [Chromium 证书导入实现](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/ui/webui/certificate_manager/user_cert_sources.cc)
4. **在同一 Chrome 个人资料中重新打开原地址。** 导入通常无需重启。其他 Chrome 个人资料需要单独导入。服务器换发自签名证书后，重新核对并导入新证书。 [Chromium 按个人资料保存证书](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/net/server_certificate_database_service_factory.cc)

如果只剩 `server.key`，可以在服务器上用它签发包含 `IP:127.0.0.1` 的新自签名证书。先让服务端加载新证书，再把这张证书导入 Chrome。 [OpenSSL 证书签发命令](https://docs.openssl.org/3.5/man1/openssl-req/)

## 验证和排查

用同一个 Chrome 个人资料打开内网地址，在证书查看器中确认浏览器实际收到的站点证书与导入的证书指纹一致。看到旧的警告页时，可先重新打开页面，必要时按 `⌘Q` 完全退出 Chrome 后重新测试。 [Chrome DevTools 查看连接证书](https://developer.chrome.com/docs/devtools/security/#view-main-origin-certificate)

| Chrome 错误码 | 检查项 |
| --- | --- |
| `NET::ERR_CERT_AUTHORITY_INVALID` | 确认这张证书进入了当前个人资料的「受信任的证书」，并与服务端当前证书的指纹一致。 |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | 检查证书 SAN 是否覆盖实际访问的 IP 或域名。 |
| `NET::ERR_CERT_DATE_INVALID` | 检查证书有效期和本机时间。 |

错误码的含义参见 [Chromium 网络错误定义](https://chromium.googlesource.com/chromium/src/+/main/net/base/net_error_list.h)。
