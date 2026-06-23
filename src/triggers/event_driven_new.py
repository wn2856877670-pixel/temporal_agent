class EventDrivenTrigger:
    def __init__(self, cooldown_seconds: float = 10.0, iou_threshold: float = 0.01):
        """
        初始化事件触发器
        :param cooldown_seconds: 触发后的冷却时间（秒）
        :param iou_threshold: 重叠阈值（0.01代表只要边缘稍微碰到一点就算）
        """
        self.cooldown_seconds = cooldown_seconds
        self.iou_threshold = iou_threshold
        self.last_trigger_time = -999.0
        self.name = f"event_driven_{cooldown_seconds}s"

    def reset(self):
        """重置触发器状态（用于处理新视频时）"""
        self.last_trigger_time = -999.0

    def _calculate_iou(self, box1, box2) -> float:
        """计算两个检测框的交并比 (IoU)"""
        # 解析坐标 (x_min, y_min, x_max, y_max)
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2

        # 计算相交区域的坐标
        intersect_xmin = max(x1_min, x2_min)
        intersect_ymin = max(y1_min, y2_min)
        intersect_xmax = min(x1_max, x2_max)
        intersect_ymax = min(y1_max, y2_max)

        # 如果没有相交，直接返回 0
        if intersect_xmax <= intersect_xmin or intersect_ymax <= intersect_ymin:
            return 0.0

        # 计算相交面积
        intersect_area = (intersect_xmax - intersect_xmin) * (intersect_ymax - intersect_ymin)

        # 计算两个框各自的面积
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)

        # 计算并集面积
        union_area = box1_area + box2_area - intersect_area

        # 返回交并比
        return intersect_area / union_area if union_area > 0 else 0.0

    def should_invoke(self, frame_state: "FrameState", events: list) -> bool:
        """检查是否满足重叠触发条件"""
        current_time = frame_state.timestamp_seconds
        objects = frame_state.objects

        # 如果画面里连2个动物都没有，直接跳过
        if len(objects) < 2:
            return False

        # 如果还在冷却期内，不触发
        if current_time - self.last_trigger_time < self.cooldown_seconds:
            return False

        # 核心逻辑：两两比较画面中所有的动物，看看有没有重叠的
        for i in range(len(objects)):
            for j in range(i + 1, len(objects)):
                box1 = objects[i].bbox
                box2 = objects[j].bbox
                
                iou = self._calculate_iou(box1, box2)
                
                # 如果重叠度大于我们设定的极小阈值（0.01）
                if iou >= self.iou_threshold:
                    self.last_trigger_time = current_time
                    # 你可以在这里取消注释下面这行来调试看它们重叠了多少
                    # print(f"[DEBUG] 检测到重叠！动物1({objects[i].class_name}) 与 动物2({objects[j].class_name}) 的 IoU = {iou:.4f}")
                    return True

        return False