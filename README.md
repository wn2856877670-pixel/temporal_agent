# 梅花鹿异常行为检测系统

这是整理后的完整可运行版本，目标是把原来混在一起的检测、触发、大模型复核和前端展示拆成清晰模块。

## 功能

- 上传监控视频
- 使用 YOLO 检测梅花鹿目标
- 使用公鹿/穿衣公鹿分类模型识别并锁定目标公鹿
- 检测公鹿与其他鹿的近距离、重叠交互
- 支持任意两只鹿 IoU 大于阈值时触发候选事件
- 保存候选事件视频片段
- 可选调用本地 Qwen-VL 模型判断是否疑似发情
- 前端展示任务状态、检测后视频、事件片段和大模型结论

## 目录结构

```text
deer_behavior_clean/
  configs/
    config.example.json          # 默认配置，权重路径在这里改
  scripts/
    run_server.py                # 启动前端
    run_video.py                 # 命令行检测单个视频
  src/deer_behavior/
    app.py                       # FastAPI 前端后端入口
    config.py                    # 配置读取
    detection.py                 # YOLO 检测与公鹿识别
    geometry.py                  # bbox 几何计算
    interaction.py               # 候选事件触发逻辑
    event_buffer.py              # 前后帧缓存与事件截片
    qwen_vl.py                   # Qwen-VL 复核
    pipeline.py                  # 完整视频处理流程
    storage.py                   # 任务记录与文件路径
    video_utils.py               # 视频写入与浏览器兼容转码
    static/style.css             # 页面样式
```

## 安装依赖

云端如果已有 torch/torchvision 环境，可直接安装：

```bash
cd /root/autodl-tmp/deer_behavior_clean
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 配置模型路径

复制配置：

```bash
cp configs/config.example.json configs/config.json
```

修改 `configs/config.json`：

```json
{
  "detector_model": "/root/autodl-tmp/hebing_08_06/deer_detect/models/deer_detector.pt",
  "male_classifier_model": "/root/autodl-tmp/hebing_08_06/deer_detect/outputs/v35_binary_b2_positive_x4/weights/best.pt",
  "qwen_model": "/root/autodl-tmp/qwen_vl_2.5_7b"
}
```

## 启动前端

```bash
cd /root/autodl-tmp/deer_behavior_clean
python scripts/run_server.py --host 0.0.0.0 --port 6008 --config configs/config.json
```

本地 Windows 也可以：

```powershell
cd D:\hebing_08_06\deer_behavior_clean
python scripts\run_server.py --host 127.0.0.1 --port 6008 --config configs\config.example.json
```

## 命令行检测

```bash
python scripts/run_video.py \
  --input /root/autodl-tmp/1.mp4 \
  --output outputs/videos/1_result.mp4 \
  --config configs/config.json
```

## 输出位置

- 完整检测视频：`outputs/videos/`
- 浏览器兼容视频：`outputs/videos/*_browser.mp4`
- 候选事件片段：`outputs/events/`
- 任务状态：`outputs/jobs/`

## 说明

模型权重不放入本项目，只通过配置文件引用路径。没有 Qwen-VL 模型或依赖时，系统仍然会输出事件片段和规则触发结果。
