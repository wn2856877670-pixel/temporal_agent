from __future__ import annotations

import argparse
import queue
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, load_settings
from .repository import DeerRepository
from .storage import JobStore, Paths, media_path, now_text, safe_upload_name


def create_app(config_path: str | Path | None = None) -> FastAPI:
    settings = load_settings(config_path)
    paths = Paths()
    store = JobStore(paths)
    repository = DeerRepository(settings)
    job_queue: queue.Queue[str] = queue.Queue()
    app = FastAPI(title="Deer Behavior Detection")
    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "src" / "deer_behavior" / "static"), name="static")

    def worker_loop() -> None:
        while True:
            job_id = job_queue.get()
            try:
                run_job(job_id)
            finally:
                job_queue.task_done()

    def enqueue_job(job: dict) -> dict:
        job["state"] = "queued"
        job["progress"] = 0
        job["queue_position"] = job_queue.qsize() + 1
        store.save(job)
        job_queue.put(job["job_id"])
        return job

    threading.Thread(target=worker_loop, daemon=True, name="deer-detection-worker").start()

    def run_job(job_id: str) -> None:
        job = store.load(job_id)
        if job is None:
            return
        job.update(
            {
                "state": "running",
                "progress": 1,
                "queue_position": None,
                "started_at_ts": time.time(),
                "eta_seconds": None,
            }
        )
        store.save(job)

        def on_progress(data: dict) -> None:
            current = store.load(job_id) or job
            progress = int(data.get("progress", current.get("progress", 1)))
            frame = data.get("frame", current.get("frame"))
            total_frames = data.get("total_frames", current.get("total_frames"))
            started_at_ts = current.get("started_at_ts") or time.time()
            eta_seconds = estimate_eta_seconds(
                started_at_ts=started_at_ts,
                frame=frame,
                total_frames=total_frames,
                progress=progress,
            )
            current.update(
                {
                    "state": "running",
                    "progress": progress,
                    "frame": frame,
                    "total_frames": total_frames,
                    "started_at_ts": started_at_ts,
                    "eta_seconds": eta_seconds,
                    "event_count": data.get("events", current.get("event_count", 0)),
                    "target_track_id": data.get("target_track_id", current.get("target_track_id")),
                }
            )
            store.save(current)

        try:
            from .pipeline import run_video

            summary = run_video(
                job["upload_path"],
                job["output_path"],
                settings,
                progress_callback=on_progress,
                task_id=job["job_id"],
                filename=job.get("original_name"),
            )
            job = store.load(job_id) or job
            job.update(
                {
                    "state": "completed",
                    "progress": 100,
                    "finished_at_ts": time.time(),
                    "eta_seconds": 0,
                    "web_output": summary["browser_output"],
                    "events": summary["events"],
                    "event_count": summary["event_count"],
                    "result": summary["result"],
                }
            )
        except Exception as exc:
            job = store.load(job_id) or job
            repository.update_task(
                job_id,
                status="failed",
                finished_at=now_text(),
                error_message=f"{type(exc).__name__}: {exc}",
            )
            job.update(
                {
                    "state": "failed",
                    "finished_at_ts": time.time(),
                    "eta_seconds": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        store.save(job)

    @app.get("/")
    def index(job: str | None = None) -> RedirectResponse:
        suffix = f"?job={job}" if job else ""
        return RedirectResponse(url=f"/detect{suffix}", status_code=303)

    @app.get("/detect", response_class=HTMLResponse)
    def detect_page(request: Request, job: str | None = None) -> str:
        return render_detect_page(store.list(), selected_job_id=job, request=request)

    @app.get("/analysis", response_class=HTMLResponse)
    def analysis_page(request: Request) -> str:
        return render_analysis_page(request)

    def create_uploaded_job(video: UploadFile) -> dict:
        if not video.filename:
            raise HTTPException(status_code=400, detail="请选择视频文件")
        paths.ensure()
        name = safe_upload_name(video.filename)
        upload_path = paths.uploads / name
        counter = 1
        while upload_path.exists():
            upload_path = paths.uploads / f"{Path(name).stem}_{counter}{Path(name).suffix}"
            counter += 1
        with upload_path.open("wb") as handle:
            shutil.copyfileobj(video.file, handle)
        job = store.create(video.filename, upload_path)
        repository.create_task(
            task_id=job["job_id"],
            filename=job.get("original_name"),
            input_path=upload_path,
            output_path=job.get("output_path"),
            status="queued",
            created_at=job.get("created_at"),
        )
        return enqueue_job(job)

    @app.post("/jobs")
    async def create_job(video: UploadFile = File(...)):
        job = create_uploaded_job(video)
        return RedirectResponse(url=f"/detect?job={job['job_id']}", status_code=303)

    @app.post("/api/jobs")
    async def api_create_job(video: UploadFile = File(...)):
        job = create_uploaded_job(video)
        return JSONResponse({"job": public_job(job)})

    @app.post("/jobs/clear")
    def clear_jobs():
        store.clear()
        return RedirectResponse(url="/", status_code=303)

    @app.get("/api/jobs")
    def api_jobs():
        return {"jobs": [public_job(job) for job in store.list()]}

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str):
        job = store.load(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return public_job(job)

    @app.get("/api/history/tasks")
    def api_history_tasks(limit: int = 100):
        return {"tasks": repository.query_tasks(limit=limit)}

    @app.get("/api/history/events")
    def api_history_events(
        task_id: str | None = None,
        event_type: str | None = None,
        qwen_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        limit: int | None = None,
    ):
        size = min(max(int(limit or page_size), 1), 1000)
        offset = (page - 1) * size
        events = repository.query_events(
            task_id=task_id,
            event_type=event_type,
            qwen_result=qwen_result,
            start_date=start_date,
            end_date=end_date,
            limit=size,
            offset=offset,
        )
        total = repository.count_events(
            task_id=task_id,
            event_type=event_type,
            qwen_result=qwen_result,
            start_date=start_date,
            end_date=end_date,
        )
        return {"events": [with_media_url(event) for event in events], "total": total, "page": page, "page_size": size}

    @app.get("/api/history/events/{event_id}")
    def api_history_event(event_id: int):
        event = repository.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return with_media_url(event)

    @app.get("/api/statistics/overview")
    def api_statistics_overview():
        return repository.statistics_overview()

    @app.get("/api/statistics/daily")
    def api_statistics_daily(days: int = 7):
        return repository.statistics_daily(days=days)

    @app.get("/api/statistics/event-types")
    def api_statistics_event_types():
        return repository.statistics_event_types()

    @app.get("/media/{path:path}")
    def media(path: str):
        target = (PROJECT_ROOT / path).resolve()
        try:
            target.relative_to(PROJECT_ROOT.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="禁止访问") from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(playable_media_target(target, settings.ffmpeg_path))

    return app


def estimate_eta_seconds(
    *,
    started_at_ts: float | int | None,
    frame: int | float | None,
    total_frames: int | float | None,
    progress: int | float | None,
) -> int | None:
    if not started_at_ts:
        return None
    elapsed = max(0.0, time.time() - float(started_at_ts))
    try:
        current_frame = float(frame or 0)
        total = float(total_frames or 0)
    except (TypeError, ValueError):
        current_frame = 0
        total = 0
    if current_frame > 0 and total > current_frame:
        return max(0, round(elapsed / current_frame * (total - current_frame)))
    try:
        percent = float(progress or 0)
    except (TypeError, ValueError):
        percent = 0
    if 0 < percent < 100:
        return max(0, round(elapsed * (100 - percent) / percent))
    return None


def with_media_url(event: dict) -> dict:
    item = event.copy()
    item["clip_url"] = media_url_for(item.get("clip_path"))
    return item


def public_job(job: dict) -> dict:
    item = job.copy()
    item["output_url"] = media_url_for(item.get("web_output") or item.get("output_path"))
    item["events"] = [
        {
            **event,
            "video_url": media_url_for(event.get("video_path")),
        }
        for event in item.get("events") or []
    ]
    item.pop("upload_path", None)
    item.pop("output_path", None)
    item.pop("web_output", None)
    return item


def media_url_for(path: str | Path | None) -> str:
    if path is None or str(path).strip() == "":
        return ""
    clip = media_path(existing_playable_media(path) or path)
    return f"/media/{clip}" if clip else ""


def existing_playable_media(path: str | Path) -> Path | None:
    target = Path(path)
    if target.stem.endswith("_browser"):
        mp4 = target.with_suffix(".mp4")
        if mp4.exists() and mp4.stat().st_size > 1024:
            return mp4
        return target if target.exists() else None
    if not target.exists():
        return None
    for suffix in (".mp4", ".webm"):
        candidate = target.with_name(f"{target.stem}_browser{suffix}")
        if candidate.exists() and candidate.stat().st_size > 1024:
            return candidate
    return None


def playable_media_target(target: Path, ffmpeg_path: str = "") -> Path:
    existing = existing_playable_media(target)
    if existing is not None:
        return existing
    if target.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
        return target
    try:
        from .video_utils import make_browser_mp4, publish_media_file

        converted = make_browser_mp4(target, ffmpeg_path)
        if converted is not None:
            publish_media_file(converted)
    except Exception:
        converted = None
    return converted or target


def render_index(jobs: list[dict]) -> str:
    return render_detect_page(jobs)


def render_detect_page(
    jobs: list[dict],
    *,
    selected_job_id: str | None = None,
    request: Request | None = None,
) -> str:
    selected = escape(selected_job_id or "")
    content = f"""
      <section class="detect-toolbar">
        <div>
          <div class="kicker">DEER BEHAVIOR MONITOR</div>
          <h1>异常行为检测工作台</h1>
          <p>上传视频后自动进入后台队列，页面刷新不会中断检测任务。</p>
        </div>
      </section>

      <section class="detect-overview-grid">
        <section class="panel upload-panel detect-upload-card">
          <div class="section-head">
            <div>
              <h2>上传待检测视频</h2>
              <p>支持 mp4、avi、mov、mkv，上传完成后进入检测队列。</p>
            </div>
          </div>
          <form class="upload" id="upload-form" action="/jobs" method="post" enctype="multipart/form-data">
            <label class="file-box">
              <input id="video-file" type="file" name="video" accept=".mp4,.avi,.mov,.mkv" required>
              <span>选择文件</span>
            </label>
            <div class="file-info" id="file-info">未选择文件</div>
            <button type="submit">开始检测</button>
          </form>
          <div class="submit-status" id="submit-status" aria-live="polite">
            <span class="status-dot"></span>
            <div>
              <b>正在上传并启动检测</b>
              <p id="upload-status-text">视频保存完成后会自动进入检测队列。</p>
              <div class="upload-progress">
                <span id="upload-percent">0%</span>
                <div class="progress"><span id="upload-progress-bar" style="width:0%"></span></div>
              </div>
            </div>
          </div>
        </section>

        <section class="panel detect-stat-card" id="current-status-card">
          <span>当前任务</span>
          <b>-</b>
          <p>暂无任务</p>
        </section>

        <section class="panel detect-stat-card" id="current-progress-card">
          <span>检测进度</span>
          <b>0%</b>
          <div>
            <div class="progress"><span style="width:0%"></span></div>
            <p>等待上传视频</p>
          </div>
        </section>
      </section>

      <section class="detect-main-grid">
        <section class="panel current-panel">
          <div class="section-head">
            <div>
              <h2>当前任务与检测结果</h2>
            </div>
          </div>
          <div id="task-detail" class="task-detail skeleton">正在加载任务状态</div>
        </section>

        <section class="panel task-list-panel">
          <div class="section-head">
            <div>
              <h2>最近任务</h2>
              <p>点击切换详情</p>
            </div>
          </div>
          <div id="task-list" class="task-list loading">正在加载任务列表</div>
        </section>
      </section>
      <script>window.__SELECTED_JOB_ID__ = "{selected}";</script>
    """
    return render_shell("异常行为检测", "detect", content, detect_script(), request=request)


def render_analysis_page(request: Request | None = None) -> str:
    content = """
      <section class="page-head">
        <div>
          <div class="kicker">DATA ANALYSIS</div>
          <h1>数据分析</h1>
        </div>
        <span class="head-note">候选事件、Qwen 确认异常与历史记录</span>
      </section>

      <section class="metrics-grid">
        <div class="metric"><span>今日检测任务</span><b id="today-tasks">0</b></div>
        <div class="metric"><span>今日候选事件</span><b id="today-events">0</b></div>
        <div class="metric"><span>今日确认异常</span><b id="today-abnormal">0</b></div>
        <div class="metric"><span>累计确认异常</span><b id="total-abnormal">0</b></div>
      </section>

      <section class="chart-grid">
        <div class="panel chart-panel">
          <div class="section-head"><h2>最近 7 天候选事件趋势</h2></div>
          <div id="daily-chart" class="chart"></div>
        </div>
        <div class="panel chart-panel">
          <div class="section-head"><h2>候选触发规则统计</h2></div>
          <div id="event-type-chart" class="chart"></div>
        </div>
      </section>

      <section class="panel history-panel">
        <div class="section-head">
          <div>
            <h2>历史行为事件</h2>
            <p>触发规则是候选来源，不等同于闻嗅、骑跨等最终行为分类。</p>
          </div>
        </div>
        <form class="filters" id="history-filters">
          <label>开始日期 <input type="date" name="start_date"></label>
          <label>结束日期 <input type="date" name="end_date"></label>
          <label>Qwen 结论
            <select name="qwen_result">
              <option value="">全部</option>
              <option value="异常">确认异常</option>
              <option value="正常">正常</option>
              <option value="待复核">待复核</option>
              <option value="复核失败">复核失败</option>
            </select>
          </label>
          <button type="submit">筛选</button>
          <button class="ghost-button" type="button" id="reset-history">重置</button>
        </form>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>发生时间</th>
                <th>关联任务</th>
                <th>候选来源</th>
                <th>持续时间</th>
                <th>公鹿 ID</th>
                <th>目标鹿 ID</th>
                <th>Qwen 结论</th>
                <th>置信度</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="history-events-body">
              <tr><td colspan="9">正在加载历史事件</td></tr>
            </tbody>
          </table>
        </div>
        <div class="pagination">
          <span id="history-page-info">-</span>
          <div>
            <button class="ghost-button" type="button" id="prev-page">上一页</button>
            <button class="ghost-button" type="button" id="next-page">下一页</button>
          </div>
        </div>
      </section>
    """
    return render_shell("数据分析", "analysis", content, analysis_script(), include_echarts=True, request=request)


def render_shell(
    title: str,
    active: str,
    content: str,
    script: str,
    *,
    include_echarts: bool = False,
    request: Request | None = None,
) -> str:
    echarts = '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>' if include_echarts else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - 梅花鹿异常行为检测系统</title>
  <link rel="stylesheet" href="/static/style.css">
  {echarts}
</head>
<body>
  <aside class="sidebar">
    <div class="brand">梅花鹿异常行为检测系统</div>
    <nav class="nav-list">
      <a class="nav {'active' if active == 'detect' else ''}" href="/detect">异常行为检测</a>
      <a class="nav {'active' if active == 'analysis' else ''}" href="/analysis">数据分析</a>
    </nav>
    <form action="/jobs/clear" method="post">
      <button class="side-button" type="submit">清空任务</button>
    </form>
  </aside>
  <main class="main">
    {content}
  </main>
  <script>{shared_script()}</script>
  <script>{script}</script>
</body>
</html>"""


def shared_script() -> str:
    return """
    async function fetchJson(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(url + ' ' + response.status);
      return response.json();
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[ch]));
    }

    function formatSeconds(value) {
      if (value === null || value === undefined || value === '') return '-';
      const number = Number(value);
      if (!Number.isFinite(number)) return '-';
      if (number >= 3600) return Math.floor(number / 3600) + '小时' + Math.floor(number % 3600 / 60) + '分';
      if (number >= 60) return Math.floor(number / 60) + '分' + Math.round(number % 60) + '秒';
      return Math.round(number) + '秒';
    }

    function formatDurationValue(value) {
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(1) + ' 秒' : '-';
    }

    function stateText(state) {
      return ({queued: '排队中', running: '检测中', completed: '已完成', failed: '失败'}[state]) || state || '-';
    }

    function triggerLabel(value) {
      const labels = {
        any_pair_iou: '候选触发：任意两鹿重叠',
        overlap_iou: '候选触发：目标公鹿重叠',
        near_distance: '候选触发：目标公鹿靠近',
        male_near: '候选触发：目标公鹿靠近'
      };
      return labels[value] || (value ? '候选触发：' + value : '候选事件（未分类）');
    }

    function qwenLabel(value) {
      return value || '待复核';
    }

    function pillClass(value) {
      if (value === '异常') return 'failed';
      if (value === '正常') return 'completed';
      if (value === '复核失败') return 'failed';
      return 'queued';
    }
    """


def detect_script() -> str:
    return """
    let selectedJobId = window.__SELECTED_JOB_ID__ || '';
    let lastJobsSignature = '';

    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('video-file');
    const fileInfo = document.getElementById('file-info');

    if (fileInput) {
      fileInput.addEventListener('change', () => {
        const file = fileInput.files && fileInput.files[0];
        fileInfo.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : '未选择文件';
      });
    }

    if (uploadForm) {
      uploadForm.addEventListener('submit', (event) => {
        if (!window.XMLHttpRequest) return;
        event.preventDefault();
        const status = document.getElementById('submit-status');
        const statusText = document.getElementById('upload-status-text');
        const percentText = document.getElementById('upload-percent');
        const progressBar = document.getElementById('upload-progress-bar');
        const button = uploadForm.querySelector('button');
        if (status) status.classList.add('visible');
        if (button) {
          button.disabled = true;
          button.textContent = '正在上传 0%';
        }

        function setUploadProgress(percent, text) {
          const value = Math.max(0, Math.min(100, Math.round(percent)));
          if (percentText) percentText.textContent = value + '%';
          if (progressBar) progressBar.style.width = value + '%';
          if (button) button.textContent = value >= 100 ? '等待入队' : '正在上传 ' + value + '%';
          if (statusText && text) statusText.textContent = text;
        }

        function failUpload(message) {
          if (statusText) statusText.textContent = message;
          if (button) {
            button.disabled = false;
            button.textContent = '重新检测';
          }
        }

        const request = new XMLHttpRequest();
        request.open('POST', '/api/jobs');
        request.upload.addEventListener('progress', (progressEvent) => {
          if (!progressEvent.lengthComputable) {
            if (statusText) statusText.textContent = '正在上传视频，请稍候。';
            return;
          }
          setUploadProgress(progressEvent.loaded / progressEvent.total * 100, '正在上传视频。');
        });
        request.addEventListener('load', () => {
          if (request.status < 200 || request.status >= 300) {
            failUpload('上传失败，请稍后重试。');
            return;
          }
          let payload = null;
          try {
            payload = JSON.parse(request.responseText);
          } catch (error) {
            failUpload('任务创建失败，请稍后重试。');
            return;
          }
          selectedJobId = payload?.job?.job_id || selectedJobId;
          setUploadProgress(100, '上传完成，已进入检测队列。');
          if (selectedJobId) history.replaceState(null, '', '/detect?job=' + encodeURIComponent(selectedJobId));
          loadJobs();
        });
        request.addEventListener('error', () => failUpload('网络连接中断，上传失败。'));
        request.send(new FormData(uploadForm));
      });
    }

    async function loadJobs() {
      try {
        const payload = await fetchJson('/api/jobs');
        const jobs = payload.jobs || [];
        if (!selectedJobId && jobs.length) {
          const active = jobs.find((job) => job.state === 'running' || job.state === 'queued');
          selectedJobId = (active || jobs[0]).job_id;
        }
        let selectedJob = jobs.find((job) => job.job_id === selectedJobId);
        if (!selectedJob && jobs.length) {
          selectedJob = jobs[0];
          selectedJobId = selectedJob.job_id;
        }
        const signature = JSON.stringify(jobs.map((job) => [
          job.job_id, job.state, job.progress, job.event_count, job.output_url,
          job.result && job.result.conclusion, job.result && job.result.confidence,
          job.result && job.result.evidence, job.eta_seconds
        ]));
        if (signature !== lastJobsSignature) {
          renderTaskKpis(jobs, selectedJob);
          renderTaskList(jobs);
          renderTaskDetail(selectedJob);
          lastJobsSignature = signature;
        }
      } catch (error) {
        document.getElementById('task-detail').innerHTML = '<div class="empty-state">任务状态加载失败，请稍后刷新。</div>';
      }
    }

    function renderTaskKpis(jobs, selectedJob) {
      const statusCard = document.getElementById('current-status-card');
      const progressCard = document.getElementById('current-progress-card');
      if (statusCard) {
        const runningCount = jobs.filter((job) => job.state === 'running' || job.state === 'queued').length;
        statusCard.innerHTML = selectedJob ? `
          <span>当前任务</span>
          <b>${stateText(selectedJob.state)}</b>
          <p>${escapeHtml(selectedJob.original_name || '-')}</p>
          <small>${runningCount} 个任务正在排队或检测</small>
        ` : `
          <span>当前任务</span>
          <b>-</b>
          <p>暂无任务</p>
          <small>上传视频后自动开始</small>
        `;
      }
      if (progressCard) {
        const progress = Number(selectedJob?.progress || 0);
        progressCard.innerHTML = `
          <span>检测进度</span>
          <b>${progress}%</b>
          <div>
            <div class="progress"><span style="width:${progress}%"></span></div>
            <p>${selectedJob ? runningMeta(selectedJob) : '等待上传视频'}</p>
          </div>
        `;
      }
    }

    function renderTaskList(jobs) {
      const list = document.getElementById('task-list');
      if (!list) return;
      if (!jobs.length) {
        list.className = 'task-list';
        list.innerHTML = '<div class="empty-state">暂无检测任务，请先上传视频。</div>';
        return;
      }
      list.className = 'task-list';
      list.innerHTML = jobs.slice(0, 12).map((job) => `
        <button class="task-row ${job.job_id === selectedJobId ? 'selected' : ''}" type="button" data-job="${escapeHtml(job.job_id)}">
          <span class="task-status-stack">
            <span class="pill ${escapeHtml(job.state)}">${stateText(job.state)}</span>
            <span class="task-percent">${Number(job.progress || 0)}%</span>
          </span>
          <span class="task-row-name">${escapeHtml(job.original_name || '-')}</span>
          <span class="task-row-meta">${escapeHtml(job.created_at || '-')} · 候选 ${Number(job.event_count || 0)} 个</span>
        </button>
      `).join('');
      list.querySelectorAll('.task-row').forEach((row) => {
        row.addEventListener('click', () => {
          selectedJobId = row.dataset.job;
          history.replaceState(null, '', '/detect?job=' + encodeURIComponent(selectedJobId));
          lastJobsSignature = '';
          loadJobs();
        });
      });
    }

    function renderTaskDetail(job) {
      const detail = document.getElementById('task-detail');
      if (!detail) return;
      if (!job) {
        detail.className = 'task-detail';
        detail.innerHTML = '<div class="empty-state">暂无当前任务。</div>';
        return;
      }
      const progress = Number(job.progress || 0);
      const result = job.result || {};
      const events = job.events || [];
      const qwenConclusion = result.conclusion || (job.state === 'completed' ? '正常' : '处理中');
      const qwenClass = qwenStatusClass(qwenConclusion);
      const qwenEvidence = result.evidence || (job.state === 'completed' ? '未返回额外依据。' : '模型结果尚未返回，系统正在处理检测任务。');
      const video = job.output_url ? `<video controls preload="metadata" src="${escapeHtml(job.output_url)}"></video>` : '<div class="video-placeholder">检测视频将在处理完成后显示</div>';
      detail.className = 'task-detail';
      detail.innerHTML = `
        <div class="task-summary">
          <div>
            <span class="pill ${escapeHtml(job.state)}">${stateText(job.state)}</span>
            <h3>${escapeHtml(job.original_name || '-')}</h3>
            <p>${runningMeta(job)}</p>
          </div>
          <div class="task-progress">
            <span>${progress}%</span>
            <div class="progress"><span style="width:${progress}%"></span></div>
          </div>
        </div>
        <div class="result-layout">
          <div class="video-pane">${video}</div>
          <aside class="result-pane">
            <div class="result-card ${qwenClass}">
              <div class="qwen-head">
                <span class="label">Qwen-VL 结论</span>
                <span class="qwen-badge">${escapeHtml(qwenConclusion)}</span>
              </div>
              <div class="confidence-row">
                <span>置信度</span>
                <b>${escapeHtml(result.confidence ?? '-')}</b>
              </div>
              <div class="evidence-box">${escapeHtml(qwenEvidence)}</div>
            </div>
            <div class="event-summary">
              <div class="summary-title">
                <b>候选事件摘要</b>
                <span>${events.length} 个候选</span>
              </div>
              <p>Qwen 确认异常 ${events.filter((event) => event.qwen_result?.conclusion === '异常').length} 个。</p>
              ${renderEventDetails(events)}
            </div>
          </aside>
        </div>
      `;
    }

    function runningMeta(job) {
      if (job.state === 'queued') {
        return `${job.queue_position ? '队列位置 ' + job.queue_position : '等待检测资源'} · 预计时间计算中`;
      }
      if (job.state === 'failed') return job.error || '检测失败';
      if (job.state === 'completed') return `检测完成 · 候选事件 ${job.event_count || 0} 个`;
      const frame = job.frame && job.total_frames ? ` · 进度帧 ${job.frame}/${job.total_frames}` : '';
      const target = job.target_track_id !== undefined && job.target_track_id !== null ? `目标公鹿 ID：${job.target_track_id}` : '正在识别目标公鹿';
      return `${target}${frame} · 预计剩余 ${formatSeconds(job.eta_seconds)}`;
    }

    function qwenStatusClass(value) {
      if (value === '异常') return 'qwen-abnormal';
      if (value === '正常') return 'qwen-normal';
      if (value === '复核失败') return 'qwen-failed';
      return 'qwen-pending';
    }

    function renderEventDetails(events) {
      if (!events.length) return '<div class="muted">尚未触发候选事件。</div>';
      return `
        <details class="events">
          <summary>展开候选事件详情</summary>
          <div class="event-list">
            ${events.map((event, index) => {
              const qwen = event.qwen_result || {};
              const video = event.video_url
                ? `<video controls preload="metadata" src="${escapeHtml(event.video_url)}"></video><a class="table-link" href="${escapeHtml(event.video_url)}" download>下载片段</a>`
                : '<div class="muted">片段暂不可用</div>';
              return `<article class="event">
                <h4>候选事件 ${index + 1}</h4>
                <p>${triggerLabel(event.reason)}</p>
                <p>时间：${Number(event.timestamp_seconds || 0).toFixed(2)} 秒</p>
                <p>Qwen-VL：${escapeHtml(qwen.conclusion || '待复核')} · ${escapeHtml(qwen.confidence ?? '-')}</p>
                <p>${escapeHtml(qwen.evidence || '')}</p>
                ${video}
              </article>`;
            }).join('')}
          </div>
        </details>`;
    }

    loadJobs();
    setInterval(loadJobs, 2500);
    """


def analysis_script() -> str:
    return """
    let historyPage = 1;
    const pageSize = 12;

    function text(id, value) {
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    }

    async function loadOverview() {
      const [overview, daily, types] = await Promise.all([
        fetchJson('/api/statistics/overview'),
        fetchJson('/api/statistics/daily?days=7'),
        fetchJson('/api/statistics/event-types')
      ]);
      text('today-tasks', overview.today_tasks ?? 0);
      text('today-events', overview.today_events ?? 0);
      text('today-abnormal', overview.today_abnormal ?? 0);
      text('total-abnormal', overview.total_abnormal ?? 0);
      renderDailyChart(daily);
      renderTypeChart(types);
    }

    function renderDailyChart(rows) {
      const node = document.getElementById('daily-chart');
      if (!node || !window.echarts) return;
      const chart = echarts.init(node);
      chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 42, right: 20, top: 24, bottom: 30 },
        xAxis: { type: 'category', data: rows.map((item) => item.date) },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{ type: 'line', smooth: true, symbolSize: 6, data: rows.map((item) => item.count) }]
      });
      window.addEventListener('resize', () => chart.resize());
    }

    function renderTypeChart(rows) {
      const node = document.getElementById('event-type-chart');
      if (!node || !window.echarts) return;
      const chart = echarts.init(node);
      chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 42, right: 20, top: 24, bottom: 56 },
        xAxis: { type: 'category', data: rows.map((item) => triggerLabel(item.event_type)), axisLabel: { rotate: 18 } },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{ type: 'bar', data: rows.map((item) => item.count) }]
      });
      window.addEventListener('resize', () => chart.resize());
    }

    function historyParams() {
      const form = document.getElementById('history-filters');
      const params = new URLSearchParams({ page: String(historyPage), page_size: String(pageSize) });
      if (!form) return params;
      const data = new FormData(form);
      for (const [key, value] of data.entries()) {
        if (value) params.set(key, value);
      }
      return params;
    }

    async function loadHistory() {
      const body = document.getElementById('history-events-body');
      if (body) body.innerHTML = '<tr><td colspan="9">正在加载历史事件</td></tr>';
      try {
        const payload = await fetchJson('/api/history/events?' + historyParams().toString());
        renderEventTable(payload.events || []);
        renderPager(payload.total || 0, payload.page || historyPage, payload.page_size || pageSize);
      } catch (error) {
        if (body) body.innerHTML = '<tr><td colspan="9">历史事件加载失败</td></tr>';
      }
    }

    function renderEventTable(rows) {
      const body = document.getElementById('history-events-body');
      if (!body) return;
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="9">暂无符合条件的历史事件</td></tr>';
        return;
      }
      body.innerHTML = rows.map((event) => {
        const video = event.clip_url ? `<a class="table-link" href="${escapeHtml(event.clip_url)}" target="_blank" rel="noopener">查看片段</a>` : '-';
        const task = event.task_id ? `<a class="table-link" href="/detect?job=${encodeURIComponent(event.task_id)}">查看任务</a>` : '-';
        return `<tr>
          <td>${escapeHtml(event.created_at || '-')}</td>
          <td>${task}</td>
          <td>${escapeHtml(triggerLabel(event.event_type))}</td>
          <td>${formatDurationValue(event.duration)}</td>
          <td>${escapeHtml(event.male_track_id ?? '-')}</td>
          <td>${escapeHtml(event.target_track_id ?? '-')}</td>
          <td><span class="pill ${pillClass(event.qwen_result)}">${escapeHtml(qwenLabel(event.qwen_result))}</span></td>
          <td>${escapeHtml(event.qwen_confidence ?? '-')}</td>
          <td>${video}</td>
        </tr>`;
      }).join('');
    }

    function renderPager(total, page, size) {
      historyPage = page;
      const pages = Math.max(1, Math.ceil(total / size));
      text('history-page-info', `第 ${page} / ${pages} 页，共 ${total} 条`);
      const prev = document.getElementById('prev-page');
      const next = document.getElementById('next-page');
      if (prev) prev.disabled = page <= 1;
      if (next) next.disabled = page >= pages;
    }

    document.getElementById('history-filters')?.addEventListener('submit', (event) => {
      event.preventDefault();
      historyPage = 1;
      loadHistory();
    });
    document.getElementById('reset-history')?.addEventListener('click', () => {
      document.getElementById('history-filters')?.reset();
      historyPage = 1;
      loadHistory();
    });
    document.getElementById('prev-page')?.addEventListener('click', () => {
      historyPage = Math.max(1, historyPage - 1);
      loadHistory();
    });
    document.getElementById('next-page')?.addEventListener('click', () => {
      historyPage += 1;
      loadHistory();
    });

    loadOverview().catch(() => {
      text('today-tasks', '-');
      text('today-events', '-');
      text('today-abnormal', '-');
      text('total-abnormal', '-');
    });
    loadHistory();
    """


def escape(value: str) -> str:
    import html

    return html.escape(value)


def render_running_meta(job: dict) -> str:
    target = job.get("target_track_id")
    target_text = f"目标公鹿 ID：{target}" if target is not None else "正在识别目标公鹿"
    frame = job.get("frame")
    total_frames = job.get("total_frames")
    frame_text = ""
    if frame and total_frames:
        frame_text = f" · 进度帧 {int(frame)}/{int(total_frames)}"
    elapsed = elapsed_seconds(job)
    elapsed_text = f"已用 {format_duration(elapsed)}" if elapsed is not None else "已用时间计算中"
    eta = job.get("eta_seconds")
    eta_text = f"预计剩余 {format_duration(eta)}" if eta is not None else "预计时间计算中"
    if job.get("state") == "queued":
        position = job.get("queue_position")
        position_text = f"队列位置 {position}" if position else "等待检测资源"
        return f"{position_text} · 预计时间计算中"
    return f"{target_text}{frame_text} · {elapsed_text} · {eta_text}"


def elapsed_seconds(job: dict) -> int | None:
    started_at_ts = job.get("started_at_ts")
    if not started_at_ts:
        return None
    try:
        return max(0, round(time.time() - float(started_at_ts)))
    except (TypeError, ValueError):
        return None


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "计算中"
    seconds = max(0, int(round(float(seconds))))
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minute}分"
    if minutes:
        return f"{minutes}分{second}秒"
    return f"{second}秒"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6008)
    parser.add_argument("--config", default="configs/config.json")
    args = parser.parse_args()

    import uvicorn

    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
