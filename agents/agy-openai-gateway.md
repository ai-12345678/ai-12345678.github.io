# 用 agy 调用 OpenAI Chat Completions 网关

在终端运行 Antigravity CLI（`agy`），通过已有的 OpenAI Chat Completions 兼容网关调用模型。示例使用网关提供的模型 ID `Gemini 4 Hydrogen`。Google 文档列出的企业网关模式最低 CLI 版本为 `1.2.15`。 [Antigravity 企业网关配置](https://docs.cloud.google.com/gemini/enterprise/docs/ai-developer-tools/connect-enterprise-gateway)

## 1. 配置网关并启动 agy

在同一个终端替换示例地址和密钥后执行。如果网关的完整接口是 `https://gateway.example.com/v1/chat/completions`，基础地址填到 `/v1`。网关有其他路径前缀时，一并保留。

```bash
export AGY_LLM_GATEWAY_URL="https://gateway.example.com/v1"
export AGY_LLM_GATEWAY_API_KEY="sk-123456"
export AGY_LLM_GATEWAY_WIRE_PROTOCOL="openai"
export AGY_LLM_GATEWAY_MODELS="Gemini 4 Hydrogen"

agy --model "Gemini 4 Hydrogen"
```

| 配置项 | 填写方式 |
| --- | --- |
| `AGY_LLM_GATEWAY_URL` | 网关的 HTTPS API 基础地址。 |
| `AGY_LLM_GATEWAY_API_KEY` | 网关发放的 API Key。 |
| `AGY_LLM_GATEWAY_WIRE_PROTOCOL` | 填 `openai`，使用 OpenAI Chat Completions 协议。 |
| `AGY_LLM_GATEWAY_MODELS` | 填网关可用的模型 ID。本例指定一个模型。 |

`--model` 为本次会话选择模型，值要与网关的模型 ID 一致。示例的模型 ID 含空格，用引号包住整个值。 [Antigravity CLI 命令参考](https://antigravity.google/docs/cli/reference/)

## 2. 验证调用

保持上面的变量已导出，用 `agy models` 查看可选模型，再用 `-p` 发送一次提示并打印响应。 [Antigravity CLI 命令参考](https://antigravity.google/docs/cli/reference/)

```bash
agy models
agy --model "Gemini 4 Hydrogen" -p "只回复 OK"
```

预期终端输出 `OK`。可在网关访问日志里核对请求路径、状态码和模型 ID。示例网关的请求路径为 `POST /v1/chat/completions`。

## 3. 常见错误

| 现象 | 检查项 |
| --- | --- |
| `401` 或「未提供令牌」 | 确认从启动 `agy` 的终端导出了 `AGY_LLM_GATEWAY_API_KEY`，密钥由当前网关发放。 |
| `404`，路径出现 `/v1/v1beta/models/...:streamGenerateContent` | 路径表明请求走了 Gemini GenerateContent。核对 `AGY_LLM_GATEWAY_WIRE_PROTOCOL` 是否设为 `openai`，然后从同一个终端重新启动 `agy`。 |
| Chat Completions 路径返回 `404` | 对照网关的完整接口检查基础地址及路径前缀，再核对模型是否在网关启用。 |
| 找不到模型 | 对照 `agy models` 的可选值与网关配置，确认 `AGY_LLM_GATEWAY_MODELS` 和 `--model` 使用同一个 ID。 |

网关变量、协议选项和故障处理见 [Antigravity 企业网关配置](https://docs.cloud.google.com/gemini/enterprise/docs/ai-developer-tools/connect-enterprise-gateway)。
