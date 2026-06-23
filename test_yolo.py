from ultralytics import YOLO

print("1. 加载模型...")
model = YOLO('yolov8n.pt')

print("2. 强行丢给显卡推理...")
# device=0 强行指定，verbose=True 逼它打印底层日志
results = model('F:/temporal_agent/1.png', device=0, verbose=True)

print("3. 推理完成！")