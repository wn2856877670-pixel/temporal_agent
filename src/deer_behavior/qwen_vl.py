from __future__ import annotations

from pathlib import Path

from .config import Settings


DEFAULT_PROMPT = """你是梅花鹿养殖场监控视频分析助手。
请判断视频片段中是否存在疑似发情相关行为。
重点关注：公鹿与母鹿持续靠近、闻嗅、追逐、爬跨、骑跨、身体重叠、短时间内反复接触。
如果证据不充分但存在明显接近或身体接触，请给出“疑似异常”。
请用以下格式回答：
[Conclusion]: 正常/疑似异常/异常
[Confidence]: 0到1之间的小数
[Evidence]: 简短中文依据
"""


class QwenVLAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = None
        self.processor = None

    def available(self) -> bool:
        return (
            self.settings.enable_qwen
            and self.settings.qwen_model is not None
            and Path(self.settings.qwen_model).exists()
        )

    def analyze_video(self, video_path: Path) -> dict:
        if self.settings.force_qwen_abnormal:
            return {
                "conclusion": "异常",
                "confidence": 0.9,
                "evidence": "画面中发现两只梅花鹿发生骑跨行为，疑似发情。",
                "raw": "forced abnormal result",
            }
        if not self.available():
            return {
                "conclusion": "待复核",
                "confidence": 0.0,
                "evidence": "未配置可用 Qwen-VL 模型，已保存候选事件片段。",
                "raw": "",
            }
        try:
            return self._run_qwen(video_path)
        except Exception as exc:
            return {
                "conclusion": "复核失败",
                "confidence": 0.0,
                "evidence": f"Qwen-VL 调用失败：{type(exc).__name__}: {exc}",
                "raw": "",
            }

    def _run_qwen(self, video_path: Path) -> dict:
        from qwen_vl_utils import process_vision_info
        from transformers import AutoModelForImageTextToText, AutoProcessor

        if self.model is None or self.processor is None:
            self.model = AutoModelForImageTextToText.from_pretrained(
                str(self.settings.qwen_model),
                torch_dtype="auto",
                device_map="auto",
            )
            self.processor = AutoProcessor.from_pretrained(str(self.settings.qwen_model))

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": str(video_path), "fps": 1.0},
                    {"type": "text", "text": DEFAULT_PROMPT},
                ],
            }
        ]
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)
        generated_ids = self.model.generate(**inputs, max_new_tokens=256)
        generated_ids_trimmed = [
            output_ids[len(input_ids) :]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        raw = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        return parse_qwen_text(raw)


def parse_qwen_text(text: str) -> dict:
    conclusion = "待确认"
    confidence = 0.0
    evidence = text.strip()
    for line in text.splitlines():
        normalized = line.strip()
        if normalized.lower().startswith("[conclusion]"):
            conclusion = normalized.split(":", 1)[-1].strip()
        elif normalized.lower().startswith("[confidence]"):
            try:
                confidence = float(normalized.split(":", 1)[-1].strip())
            except ValueError:
                confidence = 0.0
        elif normalized.lower().startswith("[evidence]"):
            evidence = normalized.split(":", 1)[-1].strip()
    if "疑似异常" in conclusion:
        conclusion = "异常"
    return {
        "conclusion": conclusion,
        "confidence": confidence,
        "evidence": evidence,
        "raw": text,
    }
