"""
Standalone Qwen-VL Tester
用于脱离检测管线，单独测试大模型对视频的理解能力。
"""

import time
from pathlib import Path
from rich.console import Console

# 导入你之前写好的 Agent
from src.agent.qwen_agent import QwenTemporalAgent

console = Console()

def main():
    console.print("[bold cyan]=== Qwen-VL 独立测试工具 ===[/bold cyan]")
    
    # ==========================================
    # 1. ⚙️ 在这里配置你的测试参数
    # ==========================================
    # 替换为你想要测试的 mp4 文件绝对路径或相对路径
    video_path = r"F:/梅花鹿测试视频/正常/正常趴卧休息2.mp4" 
    
    # 填入我们之前调优好的终极版 Prompt
    test_prompt = """
    你是一个用于自动化监测梅花鹿行为的 AI 预警系统。你的核心任务是识别画面中是否出现“疑似发情或异常”的行为。若画面出现可疑迹象（如追逐、爬跨、闻嗅），可判定为“异常”
请严格按照以下格式输出你的分析报告：
【结论】：（必须是以下两种之一）
1. 🚨 发现疑似发情/异常行为！
2. ✅ 未发现异常，鹿群状态正常。
【判定依据】：说明你做出上述结论的原因。
"""
    
    # ==========================================
    # 2. 🔍 环境预检
    # ==========================================
    if not Path(video_path).exists():
        console.print(f"[bold red]❌ 找不到视频文件，请检查路径是否正确: {video_path}[/bold red]")
        return
        
    console.print(f"[dim]待测视频: {video_path}[/dim]")
    console.print(f"[dim]提示词长度: {len(test_prompt)} 字符[/dim]\n")

    # ==========================================
    # 3. 🚀 初始化模型并执行推理
    # ==========================================
    try:
        # 实例化大模型 (这里会自动加载预加载权重)
        agent = QwenTemporalAgent()
        
        console.print(f"\n[bold yellow]🧠 模型已就绪，正在分析视频，请稍候...[/bold yellow]")
        start_time = time.time()
        
        # 直接调用你的分析方法
        result = agent.analyze_video(video_path, test_prompt)
        
        elapsed_time = time.time() - start_time
        
        # ==========================================
        # 4. 📊 打印结果
        # ==========================================
        console.print(f"\n[bold green]✅ 分析完成! (耗时: {elapsed_time:.2f} 秒)[/bold green]")
        console.print("=" * 60)
        console.print(result)
        console.print("=" * 60)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ 推理过程中发生严重错误: {str(e)}[/bold red]")


if __name__ == "__main__":
    main()