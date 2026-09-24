# Codex Provider 认证逻辑说明

## 核心逻辑

1. **先检查 Provider 自己是否配置了认证方式**，例如 `env_key`、Bearer Token、Custom Auth；如果有，就直接使用 Provider 自己的认证。

2. **如果 Provider 没有配置认证**，再检查 `requires_openai_auth`：
   - `requires_openai_auth = true`：使用 Codex 登录凭据，例如 `auth.json`。
   - `requires_openai_auth = false`：不使用 Codex 登录凭据，可能以无认证方式发送请求。

## 流程图

```text
                开始
                  │
                  ▼
      Provider 是否配置了自己的认证？
   （env_key / bearer token / custom auth）
             ┌────┴────┐
            是         否
            │           │
            ▼           ▼
   使用 Provider    检查 requires_openai_auth
     自己的认证           │
                      ┌───┴───┐
                    true     false
                      │         │
                      ▼         ▼
              使用 Codex     不使用 Codex
              登录凭据       登录凭据
             （auth.json）   （可能无认证）
```

## 一句话总结

**Provider 自己的认证优先；只有 Provider 没有配置认证时，`requires_openai_auth` 才决定是否使用 Codex 的登录凭据。**

## 示例

### 使用自定义 Provider 的环境变量认证

```toml
[model_providers.oneapi]
base_url = "https://oneapi.example.com/v1"
env_key = "ONEAPI_API_KEY"
requires_openai_auth = false
```

此时认证来源为：

```bash
$ONEAPI_API_KEY
```

不会使用 Codex 的 `auth.json` 登录凭据。

### 使用 Codex 登录认证

```toml
[model_providers.oneapi]
base_url = "https://oneapi.example.com/v1"
requires_openai_auth = true
```

如果没有配置 `env_key`、Bearer Token、Custom Auth 等 Provider 自己的认证方式，则使用 Codex 登录凭据，例如：

```text
auth.json
```
