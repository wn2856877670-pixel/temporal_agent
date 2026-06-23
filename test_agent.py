import os
import httpx
from openai import OpenAI

# 1. 强制清理可能残留的系统幽灵代理
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# 2. 填好你的配置
os.environ["OPENAI_API_KEY"] = "sk-R6RkKAP5nOGTiYxY4ln2dcJ9TzUSK55QFz5o6GqbtJzF3cAt"
os.environ["OPENAI_BASE_URL"] = "https://api.openai-proxy.org/v1"

print("正在测试连接...")
try:
    # 3. 核心魔法：创建一个强行不验证 SSL 证书的客户端！
    custom_http_client = httpx.Client(verify=False)
    
    client = OpenAI(http_client=custom_http_client)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "你好，测试一下网络。请回复'网络正常'。"}]
    )
    print("✅ 连接成功！大模型回复：", response.choices[0].message.content)
except Exception as e:
    print("❌ 连接失败，详细报错信息：", e)