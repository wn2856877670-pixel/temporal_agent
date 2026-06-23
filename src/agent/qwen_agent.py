# src/agent/qwen_agent.py
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info

class QwenTemporalAgent:
    def __init__(self, model_path="E:/Qwen/Qwen2.5-VL-7B-Instruct"):
        print("⏳ 正在加载本地 Qwen-VL 模型到显存，请稍候...")
        self.processor = AutoProcessor.from_pretrained(model_path)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        print("✅ 模型加载完毕！")

    def analyze_video(self, video_path: str, context_prompt: str) -> str:
        """接收本地视频路径并进行行为分析"""
        print(f"🚀 开始分析视频: {video_path}")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video",
                        "video": video_path,
                        # 【核心防爆点】60秒视频太长，绝对不能用 fps=1.0。
                        # n_frames=16 表示不管视频多长，系统会均匀从中抽取 16 帧发给大模型。
                        # 16 帧对于判断动物行为的上下文已经足够了。
                    
                       # "resized_height": 280, 
                        #"resized_width": 280, 
                        # 【核心救命参数 2】严格限制帧数：无论视频多长，只均匀截取 8 张图！
                        "fps": 1.0,
                    },
                    {
                        "type": "text",
                        "text": context_prompt
                    }
                ]
            }
        ]

        # 1. 渲染模板
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        # 2. 读取视频并抽帧
        image_inputs, video_inputs = process_vision_info(messages)
        # 3. 构建张量
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        ).to(self.model.device)

        # 4. 推理
        with torch.no_grad():
            torch.cuda.empty_cache()
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False
            )

        # 5. 解码
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, outputs)
        ]
        result = self.processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True
        )[0]
        
        return result