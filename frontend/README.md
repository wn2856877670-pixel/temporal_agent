# React 梅花鹿监测前端

独立的 React + TypeScript + Vite 应用，Axios 调用 REST API，React Router 管理路由，ECharts 展示统计图。原有 Python 页面及后端业务文件均保留。

## API 核对结论

2026-09-17 检查本地源码及指定云端：当前服务是 **FastAPI**，并没有 Spring Boot 项目或其接口文档。前端按实际接口适配，不假设另有 Java API。若后续切换 Spring Boot，优先保持下列 JSON 契约；字段不同时集中修改 `src/api.ts` 和 `src/types.ts`。

| 功能 | 接口 | 契约 |
| --- | --- | --- |
| 上传 | POST /api/jobs | multipart 字段 video；返回 {job} |
| 任务列表、进度 | GET /api/jobs、/api/jobs/{id} | 列表 {jobs}；详情 Task；每 3 秒轮询 |
| 历史任务 | GET /api/history/tasks?limit=1000 | {tasks}；前端本地筛选、每页 10 条 |
| 历史事件 | GET /api/history/events | task_id、start_date、end_date、event_type、qwen_result、page、page_size；返回 {events,total,page,page_size} |
| 事件详情 | GET /api/history/events/{id} | BehaviorEvent |
| 概览 | GET /api/statistics/overview | 累计/今日任务、候选事件、异常数 |
| 趋势 | GET /api/statistics/daily?days=7 | [{date,count}] |
| 类型 | GET /api/statistics/event-types | [{event_type,count}] |
| 视频 | GET /media/... | 经 Nginx 分段加载 |

`any_pair_iou` 等表示触发规则，不表示骑跨/闻嗅等已确认行为。看板统计候选触发类型，并明确行为分类未提供。数据库异常计数包含现有后端将“疑似异常”映射为“异常”的记录。候选为零时显示“未复核”，避免把规则未触发误称为 Qwen 正常判断。

## 本地开发

Node.js 20.19+ 或 22+。先在 VS Code Remote SSH 中转发云端 **6008** 到本地；本应用不创建 SSH 隧道。

```powershell
cd D:\hebing_08_06\deer_behavior_clean\frontend
npm ci
npm run dev
```

访问 http://127.0.0.1:5173 。Vite 将 `/api`、`/media` 转发到本地 6008。若 VS Code 分配了其他端口，将 `.env.example` 复制为 `.env.local` 并修改 `API_PROXY_TARGET`。不需要安装本地模型权重。

```bash
npm run build
npm test
```

## 页面与目录

```text
src/
  main.tsx       React 入口
  App.tsx        导航、上传、看板、任务、事件列表和回放
  api.ts         Axios 客户端、接口适配、媒体版本参数
  types.ts       Task / BehaviorEvent / Statistics 等类型
  hooks.ts       可取消、不会重叠的轮询请求
  components.tsx 播放器、ECharts、标签、分页和状态组件
  style.css      响应式后台布局
tests/           浏览器流程验收（接口模拟，不触发 GPU）
```

- `/dashboard`：数据看板、最近任务。
- `/analyze?task=...`：上传、状态进度、完整处理视频、Qwen 结果、候选片段。
- `/tasks`：历史任务，支持任务名/编号、日期、状态筛选。
- `/events`：历史事件，服务端日期/任务/类型/结论筛选分页。
- `/events/:id`：片段回放、时间区间、置信度、结论及可取得的依据。

路由刷新由 Vite 或 Nginx `try_files` 回退到 index.html。检测在服务器执行，切换页面/刷新不会取消已创建的任务。上传尚未完成时刷新浏览器会中断传输，路由切换则保留上传状态。完整播放器只在任务完成时加载，URL 追加完成时间；可手动重载、单独打开和下载。

## 云端部署（并行保留旧页面）

新版本默认占用 **6009**，旧版 6008 保持原样。先启动原后端，再启动独立的新前端 Nginx：

```bash
cd /root/autodl-tmp/deer_behavior_clean
./scripts/start_cloud_stack.sh  # 仅在原服务未运行时执行
install -d -m 755 /var/www/deer-react
cp -r frontend/dist/. /var/www/deer-react/
find /var/www/deer-react -type d -exec chmod 755 {} \;
find /var/www/deer-react -type f -exec chmod 644 {} \;
nginx -t -c /root/autodl-tmp/deer_behavior_clean/deploy/nginx_react.conf
nginx -c /root/autodl-tmp/deer_behavior_clean/deploy/nginx_react.conf
```

将本地 `frontend/dist/` 上传到云端同名目录，再按上述命令发布到 `/var/www/deer-react/`，避免放宽 `/root` 权限。Nginx 6009 提供静态前端，`/api/` 和 `/media/` 代理到现有 6008（媒体仍由旧 Nginx 提供）。VS Code 转发 **6009**，访问其显示的本地地址 `/dashboard`。不要将 Vite dev server 用作生产服务器。

后续 Nginx 配置更新使用 `nginx -s reload -c /root/autodl-tmp/deer_behavior_clean/deploy/nginx_react.conf`。仅更新 dist 不需要重启模型服务。旧页面始终通过 6008 访问。停止新前端可使用上述配置的 `nginx -s quit`，不影响旧 Nginx。

## 建议后端补充（本次未修改）

1. 历史任务服务端分页及 total，支持任务关键词、日期和状态；目前只能筛选最近 1000 条。
2. 历史事件持久化 Qwen evidence/raw。当前仅可尝试从任务 JSON 的对应事件取得；清空任务后依据可能缺失。
3. 独立 behavior_type（含未分类）及 trigger_rule 字段，提供行为类型字典和真正的行为分类统计。
4. 显式 processing_stage、后处理/模型复核进度和可靠 ETA，解决帧进度 99% 无法反映后处理耗时的问题。
5. 历史任务详情返回可播放 output_url、media_ready 和媒体版本。当前任务 JSON 被清除后只保留数据库记录，不能据绝对文件路径猜测 URL。
6. 有需要时补充上传大小/格式服务端校验、取消/重试任务、SSE/WebSocket、稳定分页排序和服务健康接口。

无真实 Spring Boot 契约与 GPU 时，不能声称通过 Spring Boot 集成或完整模型推理验收。
