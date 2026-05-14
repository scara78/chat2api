"""测试脚本 — 验证 GPT 反代网关（Web Cookie 模式）。

使用方式：
    1. 先启动服务：cd gpt && python main.py
    2. 新开终端运行：cd gpt && python test_client.py

可通过命令行参数选择测试：
    python test_client.py              # 运行所有测试
    python test_client.py health       # 只测健康检查
    python test_client.py chat         # 只测非流式对话
    python test_client.py chat_stream  # 只测流式对话
    python test_client.py image        # 只测图片生成

环境变量：
    BASE_URL=http://localhost:8700  服务地址
"""

import json
import os
import sys
import time

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    sys.exit(1)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8700")


def test_health():
    """测试健康检查。"""
    print("\n" + "=" * 60)
    print("🏥 测试 /health")
    print("=" * 60)
    resp = httpx.get(f"{BASE_URL}/health")
    print(f"  状态码: {resp.status_code}")
    print(f"  响应: {resp.json()}")
    assert resp.status_code == 200
    data = resp.json()
    if not data.get("has_token"):
        print("  ⚠️  未配置 CHATGPT_ACCESS_TOKEN！")
    else:
        print("  ✅ Token 已配置")


def test_chat():
    """测试非流式 Chat Completions。"""
    print("\n" + "=" * 60)
    print("💬 测试 POST /v1/chat/completions (非流式)")
    print("=" * 60)
    body = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "说一句话，10个字以内"}],
    }
    print("  发送请求...")
    start = time.time()
    resp = httpx.post(f"{BASE_URL}/v1/chat/completions", json=body, timeout=120)
    elapsed = time.time() - start
    print(f"  状态码: {resp.status_code}")
    print(f"  耗时: {elapsed:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print(f"  模型: {data.get('model')}")
        print(f"  回复: {content}")
        print("  ✅ 通过")
    else:
        print(f"  ❌ 错误: {resp.text[:300]}")


def test_chat_stream():
    """测试流式 Chat Completions。"""
    print("\n" + "=" * 60)
    print("💬 测试 POST /v1/chat/completions (流式)")
    print("=" * 60)
    body = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "用一句话介绍自己"}],
        "stream": True,
    }
    print("  发送请求...")
    content_parts = []
    start = time.time()
    with httpx.stream("POST", f"{BASE_URL}/v1/chat/completions", json=body, timeout=120) as resp:
        print(f"  状态码: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ❌ 错误: {resp.read().decode()[:300]}")
            return
        print("  流式输出: ", end="", flush=True)
        for line in resp.iter_lines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    if "error" in chunk:
                        print(f"\n  ❌ 错误: {chunk['error']}")
                        return
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        print(delta["content"], end="", flush=True)
                        content_parts.append(delta["content"])
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
    elapsed = time.time() - start
    print()
    print(f"  耗时: {elapsed:.1f}s")
    if content_parts:
        print("  ✅ 通过")
    else:
        print("  ⚠️  未收到内容")


def test_image():
    """测试图片生成。"""
    print("\n" + "=" * 60)
    print("🎨 测试 POST /v1/images/generations")
    print("=" * 60)
    body = {
        "model": "gpt-image-2",
        "prompt": "一只戴着礼帽的橘猫，水彩画风格",
        "n": 1,
        "size": "1024x1024",
    }
    print("  发送请求（图片生成可能需要 30-120 秒）...")
    start = time.time()
    resp = httpx.post(f"{BASE_URL}/v1/images/generations", json=body, timeout=600)
    elapsed = time.time() - start
    print(f"  状态码: {resp.status_code}")
    print(f"  耗时: {elapsed:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        images = data.get("data", [])
        print(f"  生成图片数: {len(images)}")
        for i, img in enumerate(images):
            url = img.get("url", "")
            if url.startswith("data:"):
                # 计算大约的图片大小
                size_kb = len(url) * 3 // 4 // 1024
                print(f"    图片 {i + 1}: data URL (~{size_kb} KB)")
            else:
                print(f"    图片 {i + 1}: {url[:100]}...")
        print("  ✅ 通过")
    else:
        print(f"  ❌ 错误: {resp.text[:300]}")


def main():
    print("🚀 GPT 反代网关测试（Web Cookie 模式）")
    print(f"   目标: {BASE_URL}")

    # 先检查服务是否在线
    try:
        httpx.get(f"{BASE_URL}/health", timeout=5)
    except httpx.ConnectError:
        print(f"\n❌ 无法连接到 {BASE_URL}")
        print("   请先启动服务: cd gpt && python main.py")
        sys.exit(1)

    tests = [
        ("health", test_health),
        ("chat", test_chat),
        ("chat_stream", test_chat_stream),
        ("image", test_image),
    ]

    # 允许通过命令行参数选择测试
    if len(sys.argv) > 1:
        selected = sys.argv[1:]
        tests = [(name, fn) for name, fn in tests if name in selected]
        if not tests:
            print(f"\n可用测试: health, chat, chat_stream, image")
            sys.exit(1)

    for name, fn in tests:
        try:
            fn()
        except httpx.ConnectError:
            print(f"\n❌ 连接断开，跳过后续测试")
            break
        except Exception as e:
            print(f"\n❌ 测试 {name} 异常: {e}")

    print("\n" + "=" * 60)
    print("🏁 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
