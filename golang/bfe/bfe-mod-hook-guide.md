# BFE mod 与 Hook 开发阅读表

核对日期：2026-10-10。仓库：[bfenetworks/bfe](https://github.com/bfenetworks/bfe)。默认分支 develop；本文固定到提交 [c95df40a3af9](https://github.com/bfenetworks/bfe/commit/c95df40a3af93d3a3b8e719e47357740bb5e8865)，避免未来分支变化影响阅读。

BFE Go mod 的请求处理核心是 Hook 回调，但完整开发还包括编译期注册、配置启用、规则加载、状态、监控和热更新。下文“推荐用途”是基于触发时机的开发建议；“注册 Hook”和“执行行为”来自该提交源码。

## 1. 对原表的修正

| 项目 | 核对结果 |
| --- | --- |
| 类型数量 | 5 种：Accept、Request、Forward、Response、Finish；原表列出的类型实际上已有 4 种 |
| Hook 数量 | 10 个；原表列出 8 个，补充 HandleFinish 与 AI 专用 HandleAfterAITargetModel |
| 官方旧回调文档 | 仍描述 9 个点；当前源码新增 AI 回调，应以本提交源码为准 |
| HandleForward | 已选定具体 backend，转发之前；位置在重试循环内 |
| HandleReadResponse | 响应对象可用，不代表流式 Body 已读取完成 |
| HandleFinish | 连接生命周期收尾；http_conn.go 的 defer 实际先 finish 再 close，不能简单理解为“物理连接关闭之后” |

依据：[回调定义](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_callback.go)、[Handler 链](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_handler_list.go)、[请求流程](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_server/reverseproxy.go)、[连接流程](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_server/http_conn.go)。

## 2. 全部 Hook 阅读表

| Hook | Handler 类型 | 源码触发时机 | 可用信息 | 开发用途（建议） | 注意事项 |
| --- | --- | --- | --- | --- | --- |
| `HandleAccept` | Accept | TCP 连接已接受，TLS 握手之前 | Session、连接、对端地址、VIP；无 HTTP 请求 | 连接准入、来源可信标记、TCP 参数 | 通常每连接一次；关闭用 `BfeHandlerClose` |
| `HandleHandshake` | Accept | TLS 握手成功后，进入应用协议处理之前 | Session、TLS 握手结果；无 HTTP 请求 | TLS 状态检查、TLS Key 日志 | 仅成功完成 TLS 握手的连接触发 |
| `HandleBeforeLocation` | Request | HTTP 请求已构造，查找 product 之前 | 请求方法、Host、URL、Header、Session、ClientAddr | 请求 ID、地理信息、路由前预处理 | product 尚未由核心路由确定；Body 不保证完整缓存在内存 |
| `HandleFoundProduct` | Request | product 已确定；普通流程查找 cluster 之前 | 上述请求信息、`req.Route.Product` | 鉴权、按产品/用户/URL 准入、标签、重定向 | 适合普通请求限流；同阶段是否已有鉴权/AI 路由结果取决于 Handler 顺序 |
| `HandleAfterLocation` | Request | 普通流程 cluster 已查找成功；AI 流程已有 AI 路由结果 | 普通流程可用 `Route.ClusterName`；AI 流程可用 AI 路由候选 | 请求头改写、URL rewrite、Body 处理准备 | AI 流程此时不保证最终 cluster/model 已选定 |
| `HandleAfterAITargetModel` | Request | AI 单次转发尝试中，最终 TargetModel 计算完成后 | AI 元信息、当前尝试 cluster、最终 `TargetModel`、已构造的 OutRequest | 目标模型允许/禁止检查、按目标模型限流 | 仅 AI 流程；换 Key/fallback 可重复触发；此时 Body model 改写及 provider Key 注入尚未完成 |
| `HandleForward` | Forward | 负载均衡选定具体 backend，设置 Trans 后，RoundTrip 之前 | Request、OutRequest、`Trans.Backend`、`Trans.Transport` | 检查实际后端、每次转发尝试的处理 | 位于重试循环，可能多次执行；不直接返回 Response |
| `HandleReadResponse` | Response | 取得响应对象，向客户端发送响应之前 | Request、Response 的状态码/Header/Body reader | 改响应头、状态、错误页面、压缩；包装 Body 实现流处理 | 不表示 Body 已读完；内部生成的部分响应也会经过此阶段 |
| `HandleRequestFinish` | Response | 代理请求处理返回后，由 FinishReq 执行收尾 | Request、HttpResponse（可能 nil）、统计、模块 Context | 访问日志、Token/费用结算、并发释放 | 响应可能失败/提前拒绝；不能当作成功完成；不能在此修改已经发送的响应 |
| `HandleFinish` | Finish | 连接处理退出时，Session.Finish 后 | Session、连接级统计和 Context；无单个 HTTP 请求参数 | 连接日志、连接级资源清理 | HTTP/1 路径 defer 中先 `c.finish()` 再 `c.close()`，不能保证 Hook 前物理连接已关闭 |

普通 HTTP 成功路径：Accept →（TLS 时 Handshake）→ BeforeLocation → 查 product → FoundProduct → 查 cluster → AfterLocation → 选 backend → Forward → 取得响应 → ReadResponse → 发送 Body → RequestFinish。一个连接可以处理多个请求，连接退出时才进入 Finish。

AI 路径：BeforeLocation → 查 product → FoundProduct（包含 API Key 校验和 AI 路由模块）→ AfterLocation → 选择转发尝试/Key → 计算 TargetModel → AfterAITargetModel → 改写 Body model、注入 provider 凭证 → 选 backend → Forward → ReadResponse → RequestFinish。换 Key/fallback 可能重新进入目标模型回调；backend 重试可能重新进入 Forward。任何提前拒绝/错误路径均可能跳过后续阶段，不能假定所有 Hook 都执行。

## 3. 函数类型

| 类型 | 严格函数签名 | 适用 Hook |
| --- | --- | --- |
| Accept | `func(*bfe_basic.Session) int` | Accept、Handshake |
| Request | `func(*bfe_basic.Request) (int, *bfe_http.Response)` | BeforeLocation、FoundProduct、AfterLocation、AfterAITargetModel |
| Forward | `func(*bfe_basic.Request) int` | Forward |
| Response | `func(*bfe_basic.Request, *bfe_http.Response) int` | ReadResponse、RequestFinish |
| Finish | `func(*bfe_basic.Session) int` | Finish |

上述简写与带参数名称的 Go 函数签名等价。AddFilter 虽然接收 interface{}，内部会断言具体函数类型；函数签名不匹配会返回注册错误。

## 4. 返回值与控制流

| 返回值 | 通用意图 | 调用点的实际约束 |
| --- | --- | --- |
| `BfeHandlerGoOn` | 继续本阶段下一个 Handler | 所有 Handler 链均以此作为继续条件 |
| `BfeHandlerResponse` | 请求阶段返回本地 Response，不访问后端 | 普通 Request 调用点进入响应处理；AI AfterAITargetModel 进入本地响应路径并关闭连接 |
| `BfeHandlerRedirect` | 按 req.Redirect 构造重定向 | 普通 Request 和 ReadResponse 调用点支持；AI AfterAITargetModel 当前 switch 未处理此值 |
| `BfeHandlerFinish` | 响应处理后结束连接 | 具体响应和状态由调用点决定；不能当成通用的自定义 429 接口 |
| `BfeHandlerClose` | 直接结束，不发送响应 | Accept/Handshake、普通 Request、AI AfterAITargetModel 有对应处理；不能推导所有调用点都支持 |

HandlerList 的统一行为是：只有 GoOn 才继续本阶段下一回调，其他返回值均中断当前链。但“中断链”不等于调用者一定执行关闭/重定向等动作。具体副作用取决于调用点 switch：Forward 和 RequestFinish 当前主要处理 Finish；Finish 阶段的返回值不再控制已进入的收尾过程。

建议：普通请求限流拒绝时使用 BfeHandlerResponse 并返回有效的 429 Response；正常放行返回 BfeHandlerGoOn, nil。创建响应时参考 bfe_basic 的响应构造函数，不能只设置状态码却返回 nil。

## 5. 模块开发机制

| 开发项 | 实现位置/方式 | 含义 |
| --- | --- | --- |
| 模块接口 | BfeModule.Name() 和 Init(cbs, whs, cr) | Name 标识模块；Init 加载配置并注册 Hook、监控和 reload |
| 编译期注册 | bfe_modules/bfe_modules.go 中 moduleList；SetModules → AddModule | Go 模块实现需要编入程序；Wasm 是另一个扩展层 |
| 配置启用 | conf/bfe.conf 的 [Server] 中 Modules | 选择已经注册的模块；仅写配置不能加载未编入的 Go mod |
| 执行阶段 | Init 中 cbs.AddFilter(Hook, handler) | 一个模块可注册多个 Hook；配置可以影响注册但没有统一的任意阶段切换机制 |
| 执行顺序 | moduleList → modulesAll → Init；AddFilter 按 PushBack 入链 | 核心顺序来自代码列表，不来自 Modules 配置行顺序 |
| product 范围 | Handler 根据 req.Route.Product 查模块规则 | 模块全局启用；每个 product 是否生效通常由模块规则判断 |
| 静态配置 | .conf；ModConfPath(root,name) = root/name/name.conf | 框架提供路径辅助；配置格式和加载由模块自己实现 |
| 动态配置 | 模块加载 .data，并向 whs 注册 reload Handler | 热更新是模块能力，不是任意变量自动热更新 |
| 请求间共享状态 | 模块对象成员；锁/原子/并发安全容器 | 不同请求可能并发进入同一个模块对象 |
| 同一请求跨 Hook 状态 | req.SetContext/GetContext | 请求 Context 本身是普通 map，跨 goroutine 访问需同步 |
| 连接状态 | session.SetContext/GetContext | Session Context 的访问器带锁；不要代替请求级状态 |
| 指标与运维 | whs 注册监控/reload，模块 Counter/Prometheus | 统计准入、拒绝、依赖错误、延迟、在途请求等 |
| 结束阶段依赖 | 提前保存后续必需数据到模块 Context | reverseproxy 在响应阶段前会清空 SvrDataConf，收尾不能假定仍可读取它 |

依据：[模块接口和初始化](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_module.go)、[代码模块列表](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/bfe_modules.go)、[配置示例](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/conf/bfe.conf)、[Request 数据结构](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_basic/request.go)、[Session 数据结构](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_basic/session.go)。

## 6. 仓库模块与 Hook 对照（34 个）

顺序来自 bfe_modules.go 的默认 moduleList。只对已启用的模块执行 Init；同一个 Hook 的 Handler 按其注册先后执行。InitModuleList 可替换默认列表，测试或定制程序的顺序可能不同。下面每个模块链接直达对应提交源码；此表是注册关系，不保证该模块对所有 product 都生效。

| 代码初始化顺序 | 模块源码 | 注册的 Hook | 主要处理方向 |
| --- | --- | --- | --- |
| 1 | [mod_trust_clientip](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_trust_clientip/mod_trust_clientip.go) | `HandleAccept` | 连接来源可信判断 |
| 2 | [mod_logid](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_logid/mod_logid.go) | `HandleAccept`、`HandleBeforeLocation` | Session/请求标识 |
| 3 | [mod_tcp_keepalive](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_tcp_keepalive/mod_tcp_keepalive.go) | `HandleAccept` | TCP keepalive |
| 4 | [mod_userid](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_userid/mod_userid.go) | `HandleFoundProduct`、`HandleReadResponse` | 请求/响应用户标识 |
| 5 | [mod_geo](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_geo/mod_geo.go) | `HandleBeforeLocation` | 地理信息 |
| 6 | [mod_tag](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_tag/mod_tag.go) | `HandleFoundProduct` | 请求标签 |
| 7 | [mod_trace](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_trace/mod_trace.go) | `HandleFoundProduct`、`HandleRequestFinish` | 追踪开始/结束 |
| 8 | [mod_cors](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_cors/mod_cors.go) | `HandleFoundProduct`、`HandleReadResponse` | 预检与跨域响应头 |
| 9 | [mod_block](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_block/mod_block.go) | `HandleAccept`、`HandleFoundProduct` | 连接/产品规则拦截 |
| 10 | [mod_prison](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_prison/mod_prison.go) | `HandleFoundProduct` | 请求限流/封禁规则 |
| 11 | [mod_auth_basic](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_auth_basic/mod_auth_basic.go) | `HandleFoundProduct` | Basic 鉴权 |
| 12 | [mod_auth_jwt](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_auth_jwt/mod_auth_jwt.go) | `HandleFoundProduct` | JWT 鉴权 |
| 13 | [mod_secure_link](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_secure_link/mod_secure_link.go) | `HandleAfterLocation` | 安全链接校验 |
| 14 | [mod_waf](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_waf/mod_waf.go) | `HandleFoundProduct` | 请求防护 |
| 15 | [mod_doh](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_doh/mod_doh.go) | `HandleFoundProduct` | DNS over HTTPS |
| 16 | [mod_redirect](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_redirect/mod_redirect.go) | `HandleFoundProduct` | HTTP 重定向 |
| 17 | [mod_static](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_static/mod_static.go) | `HandleFoundProduct` | 静态文件 |
| 18 | [mod_rewrite](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_rewrite/mod_rewrite.go) | `HandleAfterLocation` | 请求 rewrite |
| 19 | [mod_header](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_header/mod_header.go) | `HandleAfterLocation`、`HandleReadResponse` | 请求/响应头处理 |
| 20 | [mod_auth_request](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_auth_request/mod_auth_request.go) | `HandleFoundProduct` | 外部鉴权请求 |
| 21 | [mod_errors](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_errors/mod_errors.go) | `HandleReadResponse` | 错误响应处理 |
| 22 | [mod_markdown](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_markdown/mod_markdown.go) | `HandleReadResponse` | Markdown 响应渲染 |
| 23 | [mod_compress](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_compress/mod_compress.go) | `HandleReadResponse` | 响应压缩 |
| 24 | [mod_key_log](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_key_log/mod_key_log.go) | `HandleHandshake` | TLS Key 日志 |
| 25 | [mod_http_code](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_http_code/mod_http_code.go) | `HandleRequestFinish` | HTTP 状态统计 |
| 26 | [mod_access](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_access/mod_access.go) | `HandleRequestFinish`、`HandleFinish` | 请求/连接访问日志 |
| 27 | [mod_wasmplugin](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_wasmplugin/mod_wasmplugin.go) | `HandleBeforeLocation`、`HandleFoundProduct`、`HandleReadResponse` | Wasm 插件桥接（启用名称 mod_wasm） |
| 28 | [mod_unified_waf](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_unified_waf/mod_unified_waf.go) | `HandleAfterLocation` | 统一 WAF 接入（非 None 时注册） |
| 29 | [mod_ai_token_auth](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_ai_token_auth/mod_ai_token_auth.go) | `HandleFoundProduct`、`HandleAfterAITargetModel`、`HandleReadResponse`、`HandleRequestFinish` | API Key/配额鉴权、目标模型检查、结算 |
| 30 | [mod_ai_route](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_ai_route/mod_ai_route.go) | `HandleFoundProduct` | AI 路由规则 |
| 31 | [mod_body_process](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_body_process/mod_body_process.go) | `HandleAfterLocation`、`HandleReadResponse`、`HandleRequestFinish` | 请求/响应 Body 处理、usage/时序 |
| 32 | [mod_ai_rate_limit](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_ai_rate_limit/mod_ai_rate_limit.go) | `HandleAfterAITargetModel`、`HandleRequestFinish` | 目标模型并发/RPM/TPM 检查、Token 补差、并发释放 |
| 33 | [mod_access_pb3](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_access_pb3/mod_access_pb3.go) | `HandleRequestFinish`、`HandleFinish` | Protobuf 访问日志 |
| 34 | [mod_session_sticky](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_session_sticky/mod_session_sticky.go) | `HandleAfterLocation`、`HandleReadResponse` | 会话保持解码/编码 |

## 7. 限流、配额、流式输出的 Hook 选择

| 需求 | 推荐位置 | 实现要点 |
| --- | --- | --- |
| HTTP product + URL + token/uid 的 QPS/RPM | FoundProduct | 先完成身份验证，再使用可信身份生成限流 Key |
| 普通 HTTP 按 cluster 准入 | AfterLocation | 使用已确定的 cluster；不把 AI 此阶段当作最终目标 |
| AI 按实际目标 model 准入 | AfterAITargetModel | 使用 TargetModel；明确计数按逻辑请求还是按转发尝试 |
| HTTP 并发占用/释放 | FoundProduct + RequestFinish | Context 记录是否已占用；失败和提前拒绝也清理；释放须幂等 |
| AI 并发、RPM、TPM | AfterAITargetModel + RequestFinish | 可参考现有 mod_ai_rate_limit；入口检查/预占，结束补差和释放 |
| 每日/总量 Token 或金额配额 | FoundProduct + ReadResponse/Body wrapper + RequestFinish | 入口校验/预留，采集 usage，结束结算；明确中断、估算和扣费规则 |
| 限制大模型流式返回速度 | ReadResponse 中包装 res.Body | 在 Body.Read/分片读取过程中节流；SSE chunk、字符和模型 Token 不等价 |
| 后端每次尝试的观察/标记 | Forward | 每次尝试可执行，避免重复占用逻辑请求配额 |
| 访问日志、耗时和结果统计 | RequestFinish | 结合 ErrCode/Stat/Response 判断结果，处理 nil |
| 连接计数、TLS 状态、连接清理 | Accept / Handshake / Finish | 连接维度与 HTTP 请求维度分别维护 |

针对你正在使用的 HandleFoundProduct：按 product + URL + 用户身份的准入很适合此阶段；若条件依赖最终 provider/model，AI 路由可能还有映射和 fallback，应该在 AfterAITargetModel 读取 TargetModel。

现有 mod_ai_rate_limit 在 AfterAITargetModel 运行；它用 PolicyLimiterContext 避免每个逻辑请求重复准入，在 RequestFinish 用实际 usage 与预消费量补差，并释放并发。这个策略意味着 fallback 后并非自动按新模型重做整套限流检查；如果你的业务需要“每次尝试都检查新的目标模型”，需另行设计计数/预占规则。mod_ai_token_auth 的目标模型检查则按每次 AI 尝试执行。

## 8. 开发时必须区分的边界

| 边界 | 实际含义 | 开发处理 |
| --- | --- | --- |
| 连接 vs 请求 | Keepalive 和 HTTP/2 都可能让一个连接承载多个请求 | HTTP 并发占用放在请求 Context；连接统计放在 Session |
| 请求 Header vs Body | 请求对象已经存在不等于 Body 已全部缓冲 | 有大小上限地读取/peek；保持 Body 可供下游读取 |
| Response 对象 vs 完整响应 | ReadResponse 通常只保证可访问响应对象/Header/Body reader | SSE 的解析/节流在包装 Body 的读取过程中执行 |
| 逻辑请求 vs 转发尝试 | 一个请求可能换 Key、换 cluster、重试 backend | 为计数明确维度；重复回调不要重复扣配额 |
| 收尾 vs 成功 | 提前拒绝、后端失败、客户端中断也会收尾 | 检查 ErrCode、usage 完成标记、Response；处理 nil |
| 正常结束 vs exactly-once | 收尾回调不应被视为存储事务的 exactly-once 保证 | 请求内标记 + 存储操作幂等；参考 token auth 的 deducted 标记 |
| 链顺序 vs 后台并发 | 同阶段回调顺序执行，但多个请求共享模块 | 同步 Redis 调用会增加入口延迟；设置超时；共享状态需要并发保护 |
| Context map vs Context 内容 | Request 的访问器没有锁；Session 访问器有锁 | 异步任务需要自己同步，Session 内指针指向的数据也需保护 |
| 本地释放 vs 崩溃 | 进程崩溃时无法保证 RequestFinish 到达 | 分布式并发采用租约/TTL/续租，释放只针对已成功占用的名额 |
| 返回码名称 vs 实际执行 | 非 GoOn 会停止链；调用方未必处理该返回码 | 查看所选 Hook 的调用点 switch，不跨类型套用动作 |

源码里 mod_ai_token_auth 对扣费使用 deducted 标记防止重复；不应据此推断所有模块都有相同的幂等保障。新模块的释放/退款/结算要自行保证。

## 9. 阅读源码顺序

| 顺序 | 文件 | 重点 |
| --- | --- | --- |
| 1 | [bfe_callback.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_callback.go) | Hook 常量、Hook 与类型的绑定、AddFilter 分发 |
| 2 | [bfe_handler_list.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_handler_list.go) | 严格函数签名、入链顺序、GoOn 继续条件 |
| 3 | [bfe_module.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_module/bfe_module.go) | Name/Init、已启用模块初始化、modulesAll 顺序 |
| 4 | [bfe_modules.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/bfe_modules.go) | 编译进程序的模块和默认依赖顺序 |
| 5 | [http_conn.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_server/http_conn.go) | 建连、握手、请求收尾、连接 finish/close |
| 6 | [reverseproxy.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_server/reverseproxy.go) | ServeHTTP/ServeHTTPForAI、clusterInvoke、FinishReq、AI 尝试 |
| 7 | [mod_block.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_block/mod_block.go) | 同一模块注册连接与请求 Hook |
| 8 | [mod_header.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_header/mod_header.go) | 请求与响应两个方向的处理 |
| 9 | [mod_ai_rate_limit.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_ai_rate_limit/mod_ai_rate_limit.go) | Redis 依赖、并发/RPM/TPM、预消费补差 |
| 10 | [mod_ai_token_auth.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_ai_token_auth/mod_ai_token_auth.go) | 身份验证、模型权限、usage 与配额结算 |
| 11 | [mod_body_process.go](https://github.com/bfenetworks/bfe/blob/c95df40a3af93d3a3b8e719e47357740bb5e8865/bfe_modules/mod_body_process/mod_body_process.go) | Body 处理、流式 usage、时间统计 |

