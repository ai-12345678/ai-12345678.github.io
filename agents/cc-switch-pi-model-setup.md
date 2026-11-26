# 用 CC Switch 配置 Pi 的模型

以 OpenAI Chat Completions 兼容网关为例。CC Switch 从 v3.20.0 起支持管理 Pi 供应商。CC Switch 将供应商和模型写入 `models.json`，Pi 通过 `settings.json` 读取新会话的默认供应商和默认模型。 [CC Switch v3.20.0](https://cc-switch.atomgit.com/release-notes/v3.20.0-zh.html) · [Pi 配置文件](https://docs.pi.dev/latest/configuration)

## 1. 在 CC Switch 添加并启用供应商

在侧栏选「Pi」，点「添加供应商」，选择「自定义配置」。已有供应商卡片时，直接打开它编辑。 [CC Switch 添加供应商](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/zh/2-providers/2.1-add.md)

| 字段 | 示例或填写方式 |
| --- | --- |
| 供应商名称 | `我的模型网关`，用于界面显示 |
| 供应商标识 | `my-gateway`，对应 `models.json` 中 `providers` 下的键 |
| 请求地址 | `https://api.example.com/v1`，换成网关的实际 API 基础地址 |
| 接口格式 | `OpenAI Chat Completions`，对应 `openai-completions` |
| API Key | 网关签发的 API Key 或 Token |
| 模型 ID | `your-model-id`，换成网关接受的实际 ID |

如果厂商给出的完整接口是 `https://api.example.com/v1/chat/completions`，请求地址就填 `https://api.example.com/v1`，因为 Pi 会追加 `/chat/completions`。有额外路径前缀时一起保留。`/v1` 是否存在取决于网关提供的实际路径。 [Pi 自定义端点](https://docs.pi.dev/latest/models#configure-a-compatible-endpoint) · [Pi Chat Completions 实现](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts)

模型 ID 可以用「获取模型列表」选择，也可以手输。保存后回到供应商列表，如果卡片显示「启用」，就点「启用」。默认写入 `~/.pi/agent/models.json`。如果改过「Pi 配置目录」或用 `PI_CODING_AGENT_DIR` 启动，确保 CC Switch 和 Pi 指向同一个目录。 [CC Switch 配置文件](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/zh/5-faq/5.1-config-files.md)

## 2. 在 Pi 设置默认模型

启动 `pi`，输入 `/model`，在列表中高亮该供应商的模型，按 `Ctrl+S` 保存为新会话的默认模型。也可以将下面两项合入 Pi 配置目录中的 `settings.json`，保留文件中的其他设置。 [Pi 模型选择](https://docs.pi.dev/latest/models#select-a-model) · [Pi 设置](https://docs.pi.dev/latest/settings#model-and-thinking)

```json
{
  "defaultProvider": "my-gateway",
  "defaultModel": "your-model-id"
}
```

`defaultProvider` 填供应商标识，`defaultModel` 填模型 ID。项目中的 `.pi/settings.json` 可以覆盖全局默认值。恢复旧会话时，Pi 会恢复该会话记录的模型。 [Pi 设置优先级](https://docs.pi.dev/latest/settings) · [Pi 模型选择](https://docs.pi.dev/latest/models#select-a-model)

## 3. 验证配置

用平时运行 Pi 的终端执行。把 `my-gateway` 换成实际供应商标识。第二条命令使用新会话的默认模型，预期输出 `OK`。 [Pi 命令行](https://docs.pi.dev/latest/cli)

```bash
pi --list-models my-gateway
pi --no-session -p '只回复 OK'
```

| 现象 | 排查方式 |
| --- | --- |
| 列表找不到模型 | 检查卡片是否已启用，CC Switch 和 Pi 是否使用同一配置目录，网关凭据是否可用。 |
| 指定模型能用，直接运行 `pi` 选了其他模型 | 核对 `settings.json` 里的两个默认值和项目设置。一次性指定可用 `pi --provider my-gateway --model 'your-model-id'`。 |
| 选中了模型，但正文为空 | 检查网关的流式响应是否在 `choices[0].delta.content` 里返回文本。设置 `supportsFinishReason: false` 后，缺少结束标记的空流也可能显示 `stop`。 |

流式响应字段和兼容项的定义见 [Chat Completions 流式事件](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events/) 和 [Pi 模型兼容配置](https://docs.pi.dev/latest/models-configuration#openai-completions)。
