Codex System Context: 智慧农场多模态 Agent 行为分析系统

[TO CODEX / AI ASSISTANT]
You are currently analyzing the "Temporal Agent Benchmark" project. This document serves as your supreme architectural guideline. When asked to refactor, debug, or add features, strictly adhere to the technical constraints and workflows defined below.

1. 项目概览 (Project Overview)

本项目是一个用于海量监控视频（如 3.78TB 录像）的异常行为挖掘系统。主要对象是梅花鹿。
系统采用了 级联双 Agent 架构 (Cascade Multi-Agent Architecture)，通过边缘视觉过滤大面积无效视频，并将高能片段交由大语言视觉模型 (VLM) 进行精准语义判定。

1.1 技术栈 (Tech Stack)

核心语言: Python 3.10+ (采用 uv 进行环境管理)

视频处理: OpenCV (cv2)

第一级 Agent (边缘触发): YOLO (目标检测) 

第二级 Agent (深度分析): Qwen2.5-VL-7B-Instruct (使用 transformers, 本地部署)

前端大屏: Streamlit (无后端强耦合，纯文件系统轮询)

并发控制: asyncio (核心管线异步运行)

2. 系统核心工作流 (Core Workflow)

当修改核心管线代码时，必须保持以下异步解耦的数据流向不可破坏：

接入层 (CV2VideoSource): 读取视频流。

追踪与触发 (EventDrivenTrigger):

逐帧计算 Bbox 状态。

发现异常（如高重叠度跨爬）时触发警报。

环形切片 (BenchmarkRunner):

截取触发前 30 秒 + 触发后 30 秒（共 60 秒）的帧。

同步保存为 event_{timestamp}.mp4。

VLM 分析 (QwenTemporalAgent):

异步读取刚保存的 mp4 文件。

提取帧送入 Qwen-VL。

输出标准分析报告，保存为同名的 event_{timestamp}.md 文件。

前端展示 (dashboard.py):

轮询监控输出目录。

只有当 .mp4 和 .md 同时存在 时，才在页面渲染。

3. 给 Codex 的硬性开发约束 (Strict Development Rules)

3.1 视频与显存约束 (VRAM & Video Rules)



视频编码格式: 使用 OpenCV 保存网页端视频时，fourcc 必须使用 cv2.VideoWriter_fourcc(*'avc1') (H.264 编码)，绝对禁止使用 'mp4v'，否则会导致前端 Streamlit 播放器卡死或黑屏。

3.2 异步与线程约束 (Asyncio Rules)

OpenCV 的 VideoWriter 操作极其阻塞。在异步函数中写入视频时，必须使用 await asyncio.to_thread(sync_save_func, ...) 进行线程隔离。

Qwen-VL 的大模型推理函数 (model.generate) 必须使用 torch.no_grad() 包裹，且运行在独立线程中，绝不能阻塞视频流的主处理循环。

3.3 前端 (Streamlit) 约束

禁止使用 time.sleep() 控制刷新: 前端界面的自动更新或等待，应通过 Streamlit 侧边栏按钮或原生状态组件触发，严禁使用暴力睡眠阻塞主线程，否则会导致前端白屏。

防死锁机制: 前端读取文件时必须校验文件大小（os.path.getsize(vf) > 1024），防止读取到 OpenCV 刚创建但尚未 release() 的 0 字节损坏文件。

3.4 提示词注入约束 (Prompt Engineering)

如果需要修改给 Qwen-VL 的 Prompt，必须保持现有的 单样本正向接地提示 (One-Shot Prompting with Positive Grounding) 结构。

白名单机制: 必须包含【正常日常行为】（如轻度嗅探、平稳走动）作为分类选项，以降低误报率。

物理特征描述: 引导词必须要求模型基于“移动速度”、“四肢腾空”、“Bbox 空间位移”进行回答，严禁模型产生对“眼神”、“皮肤”、“心理状态”等特征的幻觉。

4. 关键文件索引 (Key File Index)

(Codex, please locate these files when asked to modify specific components)

src/benchmark/runner_new.py: 核心调度器，包含异步流控制与视频保存逻辑。

src/agent/qwen_agent.py: VLM 代理，负责构建 messages、抽取张量、执行 model.generate 并输出分析文本。

src/triggers/event_driven_new.py: YOLO 触发器规则，计算目标轨迹与物理特征阈值。

dashboard.py: Streamlit 前端大屏，负责成对读取 .mp4 与 .md 并展示。

batch_processor.py: 海量历史数据 (3.78TB) 挖掘脚本，实现无人值守的批量执行。