# dashboard.py
import streamlit as st
import os
import glob


# 1. 设置页面配置 (必须在最开头)
st.set_page_config(
    page_title="智能动物行为预警中心", 
    page_icon="🦌", 
    layout="wide"
)

st.title("🦌 智慧农场：梅花鹿行为异常监控预警系统")
st.markdown("---")

# 2. 【修复路径】使用 Windows 原生路径格式
DATA_DIR = r"F:\temporal_agent\data\event_records"

def get_latest_events():
    """获取所有生成的视频，按时间倒序排列，并过滤掉未生成完毕的残次品"""
    if not os.path.exists(DATA_DIR):
        st.error(f"❌ 找不到文件夹: {DATA_DIR}，请检查路径！")
        return []
    
    # 查找所有的 mp4 文件
    all_videos = glob.glob(os.path.join(DATA_DIR, "*.mp4"))
    valid_videos = []
    
    for vf in all_videos:
        # 【关键保命防卡死逻辑 1】：文件大小不能是 0（过滤掉 OpenCV 刚建好还在写的文件）
        if os.path.getsize(vf) < 1024: # 小于 1KB 说明是个空壳
            continue
            
        # 【关键保命防卡死逻辑 2】：只有 AI 分析报告 (.md) 也生成了，才证明整个流程走完了，可以安全展示
        report_path = vf.replace(".mp4", ".md")
        if os.path.exists(report_path):
            valid_videos.append(vf)
            
    # 按文件修改时间倒序排列
    valid_videos.sort(key=os.path.getmtime, reverse=True)
    return valid_videos

# 3. 侧边栏：刷新控制
with st.sidebar:
    st.header("⚙️ 监控面板控制")
    st.write("系统正在监听本地文件夹...")
    # 【修复自动刷新】删掉 time.sleep，使用按钮让客户明确看到你在刷新
    if st.button("手动刷新大屏 🔄", use_container_width=True):
        st.rerun()
    st.caption(f"当前监控目录:\n{DATA_DIR}")

# 4. 主干渲染逻辑
video_files = get_latest_events()

if not video_files:
    st.info("🟢 监控系统运行中。当前鹿群状态正常，暂无异常事件告警记录。")
else:
    st.success(f"🔴 发现 {len(video_files)} 条疑似异常预警记录！")
    
    # 展示最新触发的 3 条记录
    for video_path in video_files[:3]:
        report_path = video_path.replace(".mp4", ".md")
        file_name = os.path.basename(video_path)
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📹 现场触发录像")
            st.video(video_path)
            st.caption(f"源文件: {file_name}")
            
        with col2:
            st.subheader("🧠 Qwen-VL 专家分析报告")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report_content = f.read()
                st.markdown(report_content)
            else:
                with st.spinner("分析视频中，请稍候..."):
                    st.warning("视频已截获，正在生成诊断报告，请稍后刷新查看...")
        
        st.divider()