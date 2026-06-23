"""Temporal agent using Pydantic AI for structured reasoning."""
import os
import certifi
from pydantic_ai import Agent
from src.config import settings
from src.models import TemporalContext, AgentOutput
import time
# ===== 网络与认证配置区 =====


os.environ["OPENAI_BASE_URL"] = "https://api.openai-proxy.org/v1"


os.environ["OPENAI_API_KEY"] = "sk-R6RkKAP5nOGTiYxY4ln2dcJ9TzUSK55QFz5o6GqbtJzF3cAt"

# 3. 修复 SSL 证书问题
os.environ["SSL_CERT_FILE"] = certifi.where()

# 4. 强制延长超时时间到 120 秒 (防止大模型思考太慢导致断开)
os.environ["OPENAI_TIMEOUT"] = "120.0"


os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# ============================


SYSTEM_PROMPT = """You are an expert in wildlife behavior analysis. Based on the provided object movement trajectories, bounding box coordinates, and timestamps, analyze the data to determine whether the Sika deer are exhibiting any abnormal behaviors.

Normal behaviors include:
Slow walking
Head-down foraging/grazing
Standing and resting
Herd gathering

Abnormal behaviors (If detected, you MUST output a prominent WARNING):
Panicked Sprinting: Extremely fast displacement over a short period, indicating potential startlement or fleeing.
Limping/Injured: Abnormally slow movement trajectories characterized by frequent, unnatural stops.
Abnormal Collapse: Remaining completely motionless for an extended period in a non-resting area.
Stereotypic Behavior: Meaningless, repetitive pacing or circling within a highly confined space.

Note: The tracking system might mistakenly label the deer as 'cow', 'horse', or 'sheep'. Please treat all such large quadruped labels in this context as Sika deer."""


def create_temporal_agent(model_name: str = None) -> Agent[TemporalContext, AgentOutput]:
    """Create a temporal agent instance."""
    model_name = model_name or settings.default_model
    
    agent = Agent(
        f"openai:{model_name}", 
        output_type=str,
        system_prompt=SYSTEM_PROMPT,
    )
    
    return agent


def build_prompt(context: TemporalContext) -> str:
    """Build the user prompt from temporal context."""
    lines = [
        f"Current video position: frame {context.current_frame}, timestamp {context.current_timestamp:.2f}s",
        "",
        "Currently visible objects: " + (", ".join(context.active_objects) if context.active_objects else "none"),
        "",
    ]
    
    if context.event_history_summary:
        lines.extend([
            "Previous events summary:",
            context.event_history_summary,
            "",
        ])
    
    if context.recent_events:
        lines.append("Recent events:")
        for event in context.recent_events[-5]:
            lines.append(f"  - {event}")
        lines.append("")
    
    lines.append("Please provide a structured analysis of what's happening in this video segment.")
    
    return "\n".join(lines)




import time
import asyncio

async def invoke_agent(
    agent: Agent[TemporalContext, AgentOutput],
    context: TemporalContext,
) -> AgentOutput:
    prompt = build_prompt(context)
    
    print(f"[{time.strftime('%X')}] 准备发送给大模型...")
    start_time = time.time()
    
    result = await agent.run(prompt)
    
    print(f"[{time.strftime('%X')}] 大模型回复完毕！耗时: {time.time() - start_time:.2f}秒")
    
    # 强制现实世界的程序休眠 3 秒，给 API 喘息空间，防止排队暴涨
    await asyncio.sleep(3) 
    
    return AgentOutput(summary=result.output)