# BFE HTTP 转发使用说明

## 1. 一般需要配置哪些文件

简单的 HTTP 转发通常需要 **1 个主配置文件和 5 个数据配置文件**：

| 文件（相对于 conf 目录） | 用途 |
| --- | --- |
| `bfe.conf` | 主配置：设置监听端口和各数据配置文件的路径 |
| `server_data_conf/host_rule.data` | 域名归属：通过标签将域名关联到产品线（域名 → 标签 → 产品线） |
| `server_data_conf/route_rule.data` | 请求路由：配置产品线内的匹配条件，将请求转发到指定集群（产品线 → 路由条件 → 集群） |
| `server_data_conf/cluster_conf.data` | 转发策略：配置访问后端集群时的超时、健康检查和重试策略 |
| `cluster_conf/cluster_table.data` | 后端实例：定义集群、子集群及其后端实例的 IP、端口和权重（集群 → 子集群 → 实例） |
| `cluster_conf/gslb.data` | 子集群调度：配置同一集群内各子集群的流量权重 |

以下以官方完整 `conf` 目录为基础，只调整这些文件；其他默认配置保留。HTTPS 还需配置 `tls_conf/` 下的证书和 TLS 规则。

**示例目标：**将 `www.example.org` 的请求转发到 `127.0.0.1:8080`。假设 BFE 与后端在同一台机器、同一网络命名空间，BFE 监听 **8081**，避免与后端的 **8080** 冲突。

## 2. 主配置：conf/bfe.conf

在原文件的 `[Server]` 段中调整或确认以下字段：

```ini
[Server]
HttpPort = 8081
MonitorPort = 8421
HostRuleConf = server_data_conf/host_rule.data
RouteRuleConf = server_data_conf/route_rule.data
ClusterConf = server_data_conf/cluster_conf.data
ClusterTableConf = cluster_conf/cluster_table.data
GslbConf = cluster_conf/gslb.data
```

路径相对于启动参数 `-c` 指定的目录。8081 是业务入口；8421 是监控和管理端口。

## 3. 域名配置：server_data_conf/host_rule.data

```json
{
  "Version": "1",
  "DefaultProduct": null,
  "Hosts": { "demoTag": ["www.example.org", "127.0.0.1"] },
  "HostTags": { "demo_product": ["demoTag"] }
}
```

`www.example.org` 和 `127.0.0.1` 均归入标签 `demoTag`，标签归入产品线 `demo_product`。`DefaultProduct: null` 表示不指定默认产品线。

## 4. 路由配置：server_data_conf/route_rule.data

```json
{
  "Version": "1",
  "ProductRule": {
    "demo_product": [
      { "Cond": "default_t()", "ClusterName": "demo_cluster" }
    ]
  }
}
```

产品线 demo_product 的请求全部转发到 demo_cluster。`default_t()` 永远命中，通常放在最后作为兜底规则。

按 Host 或路径匹配时，可将 Cond 替换为以下表达式，JSON 内部引号必须转义：

```json
"req_host_in(\"www.example.org\") && req_path_prefix_in(\"/api/\", false)"
```

该条件匹配指定 Host 下以 `/api/` 开头的路径；`false` 表示路径匹配区分大小写。它不会自动删除路径前缀。

## 5. 集群行为：server_data_conf/cluster_conf.data

```json
{
  "Version": "1",
  "Config": {
    "demo_cluster": {
      "BackendConf": {
        "TimeoutConnSrv": 2000,
        "TimeoutResponseHeader": 50000,
        "MaxIdleConnsPerHost": 0,
        "RetryLevel": 0
      },
      "CheckConf": {
        "Schem": "http",
        "Uri": "/healthcheck",
        "Host": "www.example.org",
        "StatusCode": 200,
        "FailNum": 10,
        "CheckInterval": 1000
      },
      "GslbBasic": { "CrossRetry": 0, "RetryMax": 2 },
      "ClusterBasic": {
        "TimeoutReadClient": 30000,
        "TimeoutWriteClient": 60000,
        "TimeoutReadClientAgain": 30000
      }
    }
  }
}
```

关键参数：

- 超时和检查间隔单位为毫秒：后端连接 2 秒，等待响应头 50 秒；客户端请求体读取 30 秒、响应写回 60 秒、空闲连接 30 秒。
- 后端应提供 `/healthcheck` 并返回 200；没有该接口时，应修改 Uri。字段名称是 **Schem**。
- `FailNum: 10`：转发连续失败达到阈值后，实例标记不可用并启动健康检查；检查间隔为 1 秒。
- `RetryLevel: 0` 仍允许后端连接失败重试；`RetryMax: 2` 为子集群内重试上限，`CrossRetry: 0` 禁止跨子集群重试。

## 6. 后端实例：cluster_conf/cluster_table.data

```json
{
  "Version": "1",
  "Config": {
    "demo_cluster": {
      "demo.bfe.bj": [
        { "Addr": "127.0.0.1", "Name": "demo_1", "Port": 8080, "Weight": 10 }
      ]
    }
  }
}
```

`demo.bfe.bj` 是自定义子集群逻辑名，可用于表示地域或机房，不需要 DNS 解析。真实后端由 Addr 和 Port 指定；Weight 是子集群内实例的相对权重。增加实例时，在数组中追加对象即可。

## 7. 流量分配：cluster_conf/gslb.data

```json
{
  "Clusters": {
    "demo_cluster": { "GSLB_BLACKHOLE": 0, "demo.bfe.bj": 100 }
  },
  "Hostname": "",
  "Ts": "0"
}
```

全部流量分配给 demo.bfe.bj；黑洞子集群 GSLB_BLACKHOLE 保留为 0，分配到黑洞的请求会被丢弃。每个集群的子集群权重合计应为 **100**。

## 8. 编译、启动与验证

准备项目要求的 Go 工具链及构建依赖，在 BFE 源码根目录执行：

```bash
make
mkdir -p log
./output/bin/bfe -c conf -l log
```

`-c` 指定配置目录，`-l` 指定日志目录。使用预编译包时可跳过 make。

先检查后端健康接口，再验证 BFE 转发：

```bash
# 后端健康接口：应返回 HTTP 200
curl -i -H "Host: www.example.org" http://127.0.0.1:8080/healthcheck

# BFE 业务入口：应得到预期后端响应
curl -i -H "Host: www.example.org" http://127.0.0.1:8081/
```

本机测试不需要修改 DNS。外部访问时，域名应解析到 BFE 的可访问 IP；使用 8081 时，访问地址需要带 `:8081`。

## 9. 配置时注意这几项

1. **名称保持一致：**host_rule 的产品线 `demo_product` 对应 route_rule 的键；路由中的 `demo_cluster` 对应其余三个文件的集群名；实例表中的 `demo.bfe.bj` 对应 gslb 的子集群名。
2. **端口与地址正确：**BFE 和后端不要占用相同监听端口；容器内的 `127.0.0.1` 指向容器自身。
3. **配置必须是合法 JSON：**不能有注释、尾随逗号或未转义的内部引号。启动失败先查看前台输出和 log 目录。
4. **修改后需要生效操作：**使用当前版本支持的 reload 接口，或在本地测试中重启 BFE，再验证请求。
5. **HTTPS 需要额外配置：**设置 HttpsPort，并配置 `tls_conf/server_cert_conf.data`、`tls_conf/tls_rule_conf.data` 与实际证书；仅增加端口还不够。

参考：[BFE 官方文档](https://www.bfe-networks.net/en_us/configuration/bfe.conf/)。本文示例已检查 JSON 语法，未执行实际部署测试。

## 附录 A：条件原语与使用速查

条件原语返回布尔值，可用于路由或模块规则的 `Cond`。下面按所提供的清单整理；**实际支持范围以部署版本为准**。正文保持简版，本附录单独扩展。

**标记说明：**无标记项的调用形式已在官方在线文档中核对；带 **†** 的项未在本次可访问的官方文档中核实完整签名，只说明用途，不提供猜测的调用参数。Body 大小比较原语已出现在官方发布记录中，但其参数类型与判定细节仍需核对所用版本源码。

### A.1 通用写法

- `default_t()`：始终为真，用作兜底条件。
- `&&` 表示同时满足，`||` 表示满足任一条件，`!` 表示取反；可用括号分组。
- 常见列表参数用竖线分隔，如 `"GET|POST"`。Markdown 表格内示例使用单个值，避免竖线影响表格。
- 带 `case_insensitive` 的原语，`true` 表示忽略大小写，`false` 表示区分大小写。
- `*_hash_in` 匹配哈希分桶，常用于灰度分流；文档中哈希值范围为 0～9999。
- `req_*` 读取请求，`ses_*` 读取连接会话，`res_*` 读取响应，`bfe_*` 读取系统信息。

JSON 配置中的组合示例：

```json
{
  "Cond": "req_host_in(\"www.example.org\") && req_method_in(\"GET\") && req_path_prefix_in(\"/api/\", false)",
  "ClusterName": "demo_cluster"
}
```

### A.2 客户端 / IP / VIP / 协议

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_cip_trusted` | 判断客户端 IP 的可信标记：`req_cip_trusted()`；需结合客户端 IP 识别及信任配置 |
| `req_cip_hash_in` | 按客户端 IP 哈希分桶：`req_cip_hash_in("0-999")` |
| `req_cip_range` | 客户端 IP 位于闭区间：`req_cip_range("10.0.0.1", "10.0.0.255")` |
| `req_vip_in` | 匹配请求入口 VIP：`req_vip_in("192.0.2.10")` |
| `req_vip_range` | 匹配请求 VIP 范围：`req_vip_range("192.0.2.1", "192.0.2.20")` |
| `req_proto_match` † | 按请求协议匹配；协议名称及参数形式需核对部署版本 |
| `req_proto_secure` | 判断请求是否使用 TLS：`req_proto_secure()` |
| `req_port_in` | 匹配请求端口：`req_port_in("8081")` |
| `req_method_in` | 匹配 HTTP 方法：`req_method_in("POST")` |

VIP 指入口虚拟 IP，不是后端集群 IP。TLS 判断反映 BFE 所观察到的请求连接；前置代理终止 TLS 的场景需结合实际接入方式理解。

### A.3 Host

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_host_in` | Host 精确匹配，忽略大小写：`req_host_in("www.example.org")` |
| `req_host_regmatch` † | Host 正则匹配 |
| `req_host_tag_in` † | 匹配域名标签，例如正文中的 demoTag；与普通请求 Tag 区分 |
| `req_host_suffix_in` † | Host 后缀匹配，可用于域名分组 |

† 项的参数签名及后缀边界处理需核对源码；域名后缀匹配时应注意 `example.org` 与 `badexample.org` 的边界。

### A.4 Path / URL

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_path_in` | 路径精确匹配：`req_path_in("/api", false)` |
| `req_path_prefix_in` | 路径前缀匹配：`req_path_prefix_in("/api/", false)` |
| `req_path_suffix_in` | 路径后缀匹配：`req_path_suffix_in(".json", false)` |
| `req_path_contain` | 路径包含子串：`req_path_contain("/admin", false)` |
| `req_path_regmatch` † | 路径正则匹配 |
| `req_path_element_prefix_in` | 按路径段前缀匹配：`req_path_element_prefix_in("/api/", false)` |
| `req_url_regmatch` | URL 正则匹配：`req_url_regmatch("^/api/")` |

`req_path_prefix_in("/api", false)` 也会匹配 `/apix`；按目录边界匹配时可使用路径段原语，或组合 `/api` 精确匹配与 `/api/` 前缀匹配。正则在 JSON 中含反斜杠时还需做 JSON 转义。

### A.5 Query

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_query_key_in` | 查询参数键匹配：`req_query_key_in("uid")` |
| `req_query_key_prefix_in` | 查询参数键前缀匹配：`req_query_key_prefix_in("utm_")` |
| `req_query_exist` † | 查询参数存在性判断；与 key_in 的差异及参数形式需核对版本 |
| `req_query_value_in` | 值精确匹配：`req_query_value_in("env", "dev", false)` |
| `req_query_value_prefix_in` | 值前缀匹配：`req_query_value_prefix_in("uid", "test_", false)` |
| `req_query_value_suffix_in` | 值后缀匹配：`req_query_value_suffix_in("file", ".csv", false)` |
| `req_query_value_regmatch` † | 指定查询参数值的正则匹配 |
| `req_query_value_contain` † | 指定查询参数值的子串匹配 |
| `req_query_value_hash_in` | 值哈希分桶：`req_query_value_hash_in("uid", "0-999", false)` |

例如 `?env=dev` 可匹配上表的 env 条件。参数不存在、空值和同名多值的行为，应结合部署版本测试。

### A.6 Cookie

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_cookie_key_in` | Cookie 键匹配：`req_cookie_key_in("session_id")` |
| `req_cookie_value_in` | 值精确匹配：`req_cookie_value_in("env", "dev", false)` |
| `req_cookie_value_prefix_in` | 值前缀匹配：`req_cookie_value_prefix_in("uid", "test_", false)` |
| `req_cookie_value_suffix_in` | 值后缀匹配：`req_cookie_value_suffix_in("uid", "_beta", false)` |
| `req_cookie_value_contain` | 值包含子串：`req_cookie_value_contain("group", "beta", false)` |
| `req_cookie_value_hash_in` | 值哈希分桶：`req_cookie_value_hash_in("uid", "0-999", false)` |

Cookie 值匹配可用于分流，但仅匹配 session_id 的存在不等于验证用户已经登录。

### A.7 Header / User-Agent

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_header_key_in` | 请求头键匹配：`req_header_key_in("Authorization")` |
| `req_header_value_in` | 值精确匹配：`req_header_value_in("X-Env", "dev", false)` |
| `req_header_value_prefix_in` | 值前缀匹配：`req_header_value_prefix_in("Authorization", "Bearer ", false)` |
| `req_header_value_suffix_in` | 值后缀匹配：`req_header_value_suffix_in("X-Version", "-beta", false)` |
| `req_header_value_regmatch` † | 指定请求头值的正则匹配 |
| `req_header_value_contain` | 值包含子串：`req_header_value_contain("User-Agent", "Mobile", true)` |
| `req_header_value_hash_in` | 值哈希分桶：`req_header_value_hash_in("X-User-ID", "0-999", false)` |
| `req_ua_regmatch` † | User-Agent 正则匹配 |

`Authorization` 前缀匹配只判断格式，不验证 token 的有效性；认证需要认证模块或外部服务。

### A.8 Tag / Context

| 原语 | 用途与调用示例 |
| --- | --- |
| `req_tag_match` | 请求标签名和值匹配：`req_tag_match("env", "beta")` |
| `req_context_value_in` | 上下文值匹配：`req_context_value_in("env", "beta", false)` |

Tag 和 Context 一般由前面的模块写入，使用条件前必须确保对应数据已产生。它们不会自动读取同名 Header 或 Query；host_rule 中的域名标签也不是这里的请求标签。

### A.9 Body

| 原语 | 用途与调用形式 |
| --- | --- |
| `req_body_json_in` | 按 JSON 路径匹配值：`req_body_json_in(json_path, value_list, case_insensitive)`；三个参数依次为字符串、字符串、布尔值 |
| `req_body_json_prefix_in` † | 按 JSON 路径对值做前缀匹配 |
| `req_body_larger_than` † | 请求体大小大于指定阈值；单位、参数类型及未知长度处理需核对版本 |
| `req_body_less_than` † | 请求体大小小于指定阈值；单位、参数类型及未知长度处理需核对版本 |

`json_path` 是占位参数，不是字面值；其路径语法需以所用版本为准。可用于按请求中的 model 等字段分流。使用 Body 原语前，应确认该版本的 Body 读取或处理配置，避免假定请求体在任意 hook 都可读取。大小比较是否依据 Content-Length 或实际读取长度，本次未核实。

### A.10 Session / TLS

| 原语 | 用途与调用示例 |
| --- | --- |
| `ses_vip_range` | 会话 VIP 范围匹配：`ses_vip_range("192.0.2.1", "192.0.2.20")` |
| `ses_sip_range` | 会话服务端 IP 范围匹配：`ses_sip_range("10.0.0.1", "10.0.0.20")` |
| `ses_tls_sni_in` | TLS SNI 匹配：`ses_tls_sni_in("www.example.org")` |
| `ses_tls_client_auth` | 判断是否启用 TLS 双向认证：`ses_tls_client_auth()` |
| `ses_tls_client_ca_in` | 双向认证及客户端 CA 名称匹配：`ses_tls_client_ca_in("demo_ca")` |

SNI 是 TLS 握手中的域名，Host 是 HTTP 请求字段，两者不应混用；CA 名称需对应实际证书认证配置。双向认证开关判断不能代替完整的授权策略。

### A.11 Response

| 原语 | 用途与调用示例 |
| --- | --- |
| `res_code_in` | 响应状态码匹配：`res_code_in("503")` |
| `res_header_key_in` | 响应头键匹配：`res_header_key_in("Content-Type")` |
| `res_header_value_in` | 响应头值匹配：`res_header_value_in("Content-Type", "application/json", false)` |

响应原语应在响应已经产生的处理阶段使用，不能用于依赖未来响应的首次请求路由。Content-Type 可能带 charset 等参数，精确匹配时需要考虑实际值。

### A.12 时间

| 原语 | 用途与调用示例 |
| --- | --- |
| `bfe_time_range` | 固定时间区间：`bfe_time_range("20261010090000H", "20261010180000H")` |
| `bfe_periodic_time_range` | 日内周期区间：`bfe_periodic_time_range("090000H", "180000H", "")` |

完整日期格式为 `yyyymmddhhmmssZ`，日内时刻为 `hhmmssZ`；结尾时区字母 `H` 表示 UTC+8。第二个示例表示每天北京时间 09:00～18:00，period 使用官方示例的空字符串。

### A.13 版本核对与参考

本文未获取部署中的 BFE 版本，也未执行所有原语的解析和运行测试。因此此表是使用速查，不能直接作为某台实例的“全部已支持”清单。若需确认 † 项，应检查部署版本源码中的原语注册和参数定义（通常在 `bfe_route/condition/semant.go`），再核对构建逻辑与测试用例。

- [官方条件原语索引](https://www.bfe-networks.net/en_us/condition/condition_primitive_index/)
- [条件语法](https://www.bfe-networks.net/en_us/condition/condition_grammar/)
- [请求 URI](https://www.bfe-networks.net/en_us/condition/request/uri/) · [请求 IP](https://www.bfe-networks.net/en_us/condition/request/ip/) · [请求 Header](https://www.bfe-networks.net/en_us/condition/request/header/)
- [TLS 条件](https://www.bfe-networks.net/en_us/condition/session/tls/) · [时间条件](https://www.bfe-networks.net/en_us/condition/system/time/)
- [官方发布记录](https://github.com/bfenetworks/bfe/releases)

