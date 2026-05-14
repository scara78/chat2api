<div align="center">

# ChatGPT2API

**将 ChatGPT 网页端能力转为 OpenAI 兼容 API**

通过 Access Token 调用 ChatGPT，走订阅额度，无需 API Key 付费。
任何 OpenAI SDK 可直接对接。

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## ✨ 特性

- 🔄 **OpenAI 兼容** — 标准 `/v1/chat/completions` 和 `/v1/images/generations` 接口
- 🖼️ **图片生成** — 支持 gpt-image-2，图片保存本地并返回可访问 URL
- 🌊 **流式输出** — 支持 SSE 流式对话
- 🛡️ **绕过 Cloudflare** — 使用 curl_cffi 模拟 Chrome TLS 指纹
- 🧮 **自动 PoW** — 自动计算 Proof-of-Work token 通过反滥用验证
- 🌐 **代理支持** — HTTP / HTTPS / SOCKS5
- 🚀 **零成本** — 走 ChatGPT Plus/Pro 订阅额度，无额外 API 费用

## 📦 快速开始

### 1. 安装

```bash
git clone https://github.com/yourname/chatgpt2api.git
cd chatgpt2api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 必填：ChatGPT Access Token
CHATGPT_ACCESS_TOKEN=eyJhbGciOi...

# 必填：代理地址（需能访问 chatgpt.com）
PROXY_URL=http://127.0.0.1:7890
```

### 3. 获取 Access Token

1. 浏览器登录 [chatgpt.com](https://chatgpt.com)
2. 访问 [chatgpt.com/api/auth/session](https://chatgpt.com/api/auth/session)
3. 复制 JSON 中的 `accessToken` 字段

> Token 有效期约 10 天，过期后重新获取替换即可。

### 4. 启动

```bash
python main.py
```

服务监听 `http://0.0.0.0:8700`，API 文档：`http://localhost:8700/docs`

## 🔌 使用

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="anything",  # 随便填
    base_url="http://localhost:8700/v1",
)

# 对话
resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)

# 流式对话
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "写一首诗"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# 生成图片
resp = client.images.generate(
    model="gpt-image-2",
    prompt="一只戴着礼帽的橘猫，水彩画风格",
    size="1024x1024",
)
print(resp.data[0].url)
# → http://localhost:8700/images/xxxx.png
```

### cURL

```bash
# 对话
curl http://localhost:8700/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}'

# 流式
curl http://localhost:8700/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}],"stream":true}'

# 生成图片
curl http://localhost:8700/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-2","prompt":"a cute cat","size":"1024x1024"}'
```

### Node.js

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "anything",
  baseURL: "http://localhost:8700/v1",
});

const resp = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "hello" }],
});
console.log(resp.choices[0].message.content);
```

## 🧪 测试

```bash
python -B test_client.py              # 全部测试
python -B test_client.py health       # 健康检查
python -B test_client.py chat         # 非流式对话
python -B test_client.py chat_stream  # 流式对话
python -B test_client.py image        # 图片生成
```

## ⚙️ 配置项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CHATGPT_ACCESS_TOKEN` | Access Token（必填） | — |
| `PROXY_URL` | 出站代理（必填） | — |
| `CHATGPT_BASE_URL` | ChatGPT 地址 | `https://chatgpt.com` |
| `PORT` | 监听端口 | `8700` |
| `TIMEOUT` | 请求超时（秒） | `600` |
| `WEB_IMAGE_MODEL` | 图片生成模型 | `gpt-5-5-thinking` |
| `WEB_CHAT_MODEL` | 对话默认模型 | `gpt-4o` |

## 📁 项目结构

```
├── main.py              # 入口
├── config.py            # 配置加载
├── http_client.py       # curl_cffi 客户端（Chrome TLS 指纹）
├── routes_chat.py       # /v1/chat/completions（流式 + 非流式）
├── routes_images.py     # /v1/images/generations（图片保存本地）
├── web_client.py        # Web 图片生成完整流程
├── web_fingerprint.py   # 浏览器指纹构造
├── web_proof.py         # Proof-of-Work 计算
├── web_sse_parser.py    # SSE 流解析
├── image_utils.py       # 尺寸/比例映射
├── test_client.py       # 测试脚本
└── images/              # 生成的图片
```

## 🔧 工作原理

```
调用方 (OpenAI SDK)
    │
    ▼
┌──────────────────────────────────┐
│  FastAPI (:8700)                 │
│  curl_cffi (Chrome TLS 指纹)    │
│  PoW Token 自动计算              │
└──────────────┬───────────────────┘
               │ via Proxy
               ▼
┌──────────────────────────────────┐
│  chatgpt.com 内部 API            │
│  /backend-api/f/conversation     │
└──────────────────────────────────┘
```

1. 接收 OpenAI 格式请求
2. 用 curl_cffi 模拟 Chrome 浏览器 TLS 指纹
3. 构造完整的浏览器 Headers（User-Agent、Sec-CH-UA、OAI-Device-Id 等）
4. 计算 Proof-of-Work token 通过反滥用验证
5. 调用 ChatGPT 内部 conversation API
6. 解析 SSE 响应，转换为 OpenAI 兼容格式返回

## ⚠️ 注意事项

- 需要代理才能访问 chatgpt.com（国内直连被 Cloudflare 拦截）
- Access Token 约 10 天过期，需定期更新
- 图片生成耗时 30-60 秒，这是 ChatGPT 本身的速度
- Free 账号有使用限制，Plus/Pro 额度更充裕
- 本项目仅供学习研究，请遵守 OpenAI 使用条款

## 📄 License

MIT
