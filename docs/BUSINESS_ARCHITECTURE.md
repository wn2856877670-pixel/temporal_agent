# 梅花鹿业务架构

## 边界与任务链

旧 FastAPI 与 React 页面保留在 6008/6009；新业务版 Nginx 6010，Spring Boot 6020（仅回环地址）。
新增模块不替换 YOLO、BoT-SORT、公鹿识别、候选触发与 Qwen 算法。

React multipart 上传 → Spring Boot 保存文件 → 同一 MySQL 事务创建 QUEUED 任务、task_outbox → Redis 初始状态 → OutboxDispatcher 使用 RabbitTemplate + publisher confirm 投递 `{taskId,videoPath}` → Python claim → 原 pipeline → REVIEWING → Qwen → 内部接口归档事件 → COMPLETED → Worker ACK。

Redis 故障时数据库任务仍可查询；消息系统故障时 outbox 保留待发消息。数据库是任务状态权威，Redis 不是业务事件存储。上传接口返回 202，不等待推理或 RabbitMQ 网络确认，正常情况下发件箱在 2 秒内投递。

## 目录

- `backend/`：Java 17 / Spring Boot 3，controller/service/repository/entity/dto/config/mq/exception。
- `worker/consumer.py`：pika 手动 ACK、租约心跳、子进程监督、断线重连。
- `worker/pipeline_adapter.py`：复用原 pipeline，将结果收集为内部 API DTO；Python 不连接 MySQL。
- `src/deer_behavior/pipeline.py`：仅增加可注入 repository 和 REVIEWING 进度回调，原 run_video.py 调用方式不变。
- `frontend/src/businessApi.ts`：camelCase REST → 现有 UI 类型适配；`--mode business` 启用。
- `deploy/nginx_business.conf`：静态 React、媒体 Range、API 代理，禁止外部访问内部接口。
- `scripts/`：基础服务初始化、业务 API/Worker 启动及隔离集成测试。

## 数据库

首次启动 Hibernate 自动建表（`ddl-auto=update`，正式生产建议改用审核过的 Flyway 迁移）。

| 表 | 主要字段与约束 |
|---|---|
| analysis_task | id；task_id UNIQUE；file_name；video_path；result_video_path；status；event_count；error_message；created_at/started_at/finished_at |
| behavior_event | id；event_id UNIQUE；task_id；event_index；event_type；start_time/end_time/duration；male_track_id/target_track_id；confidence；qwen_result/qwen_confidence；clip_path；created_at；UNIQUE(task_id,event_index) |
| task_log | task_id、stage、level、message、created_at；task_id+created_at 索引 |
| task_outbox | task_id 主键、sent、next_attempt；与任务创建在同一个事务中 |

任务额外持久化 attempts、lease_token、lease_until、result_json；事件额外持久化 evidence。event_type 沿用候选触发规则，不声称它就是骑跨/闻嗅行为分类。

## Redis

Hash `deer:task:{taskId}`：status、progress、stage、processedFrames、totalFrames、updatedAt。
运行中无过期时间，COMPLETED/FAILED 后 24 小时 TTL；TTL 到期仍可从 MySQL 查询终态。Redis 暂不可用时详情接口使用数据库状态，帧数/进度可能降级；恢复后下一次心跳更新。

## RabbitMQ 与 ACK

| Exchange | Routing Key | Queue |
|---|---|---|
| deer.task.exchange（Direct） | deer.task.analyze | deer.task.queue |
| deer.task.failure.exchange（Direct） | failure | deer.task.failure.queue |
| deer.task.exchange | retry | deer.task.retry.queue |
| deer.task.exchange | dead | deer.task.dlq |

全部持久化，消息 delivery_mode=2；只传 taskId/videoPath，不传视频内容。
主队列 NACK(requeue=false) 死信进入 failure queue。Java RetryRouter 判断任务状态，再经 publisher confirm 发入延迟重试队列（默认 10 秒 TTL，回到主队列）或最终 DLQ，然后 ACK failure 消息。发布失败则 NACK(requeue=true)，不丢弃路由消息。

Worker `auto_ack=False`、`prefetch_count=1`。仅在事件事务和 COMPLETED 状态事务成功后 ACK；已完成任务的重复消息直接 ACK。异常先终止推理子进程、释放租约，再 NACK(requeue=false)。失败首次执行加最多 3 次重试，共 4 次 claim；最后进入 FAILED 与 DLQ。忙碌中的重复消息只延迟，不占执行次数。

采用至少一次处理，不宣称跨 MySQL/RabbitMQ/Redis 的分布式 exactly-once。若发布确认后应用崩溃，消息可能重发，但任务 claim 与事件唯一键会防止重复归档。单节点 classic queue 的 broker/磁盘故障仍有可靠性边界，生产建议多节点 quorum queue 与受支持的 at-least-once dead-letter 策略。

## 状态与幂等

TaskStateService 是唯一状态转换入口。先按 task_id 获取数据库行锁，再执行带预期旧状态的条件 UPDATE，检查受影响行数。
合法流转 QUEUED → RUNNING → REVIEWING → COMPLETED；处理中可进入 FAILED；终态不回退。

claim 返回不可猜测 leaseToken，所有 Worker 写请求都必须携带。每 2 秒心跳续期（默认 120 秒）；Worker 失联后重投可以接管，旧 token 被隔离。重试保留 RUNNING/REVIEWING 状态，不回退到 QUEUED。接管会重新执行原 pipeline，最多 4 次。每个 attempt 使用独立输出目录，避免旧子进程与新执行互相覆盖。

事件归档在任务行锁及事务下按 task_id/event_index 查重，数据库联合唯一键提供第二层约束。重复提交返回已有事件，不插入新行。COMPLETED 响应丢失后相同 token 的重复完成请求可安全返回。

## REST 接口

公开接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/tasks | multipart 字段 video；202 返回 taskId 与任务详情 |
| GET | /api/tasks | page/pageSize、taskId/status/startDate/endDate，1 起始分页 |
| GET | /api/tasks/{taskId} | 数据库详情，outputUrl、resultJson |
| GET | /api/tasks/{taskId}/progress | Redis 实时状态，终态由 MySQL 校正 |
| GET | /api/tasks/{taskId}/events | 该任务全部事件，按 eventIndex |
| GET | /api/events | taskId/eventType/qwenResult/startDate/endDate/page/pageSize |
| GET | /api/events/{eventId} | 路径使用数值主键 id；另有稳定 eventId UUID 字段 |
| GET | /api/statistics/overview | 累计/今日任务、候选事件、判为异常数量 |
| GET | /api/statistics/daily?days=7 | 每日候选事件数量，含无数据日期 |
| GET | /api/statistics/event-types | 候选触发类型统计 |

内部接口统一要求 `X-Internal-Token`；除 claim 外还要求 `X-Lease-Token`：

- POST `/api/internal/tasks/{taskId}/claim`：body `{owner}`；返回 claimed/leaseToken 或 alreadyCompleted/busy/terminal。
- PATCH `.../progress`：progress（0..99）、stage、processedFrames、totalFrames。
- PATCH `.../status`：status；完成时 resultVideoPath/result；失败时 errorMessage。RUNNING 必须使用 claim，不能绕过租约。
- POST `.../events`：BehaviorEvent DTO 数组；eventIndex、eventType、时间、目标编号、置信度、Qwen 结果、clipPath、evidence。
- POST `.../release`：失败释放租约并写关键日志，不立即终结任务。

视频路径必须在当前任务 results 目录下且文件存在。媒体 URL 自动附加任务完成时间，播放和轮询解耦。上传不是远程 URL 下载接口。

## 本地与云端启动

需要 Java 17、Maven、Node 20.19+、Python deer 环境及模型。不要提交 `.env`、模型和运行数据。

```bash
# Linux / WSL，在项目根目录；先填写真实随机密码
cp .env.example .env
docker compose up -d
mvn -f backend/pom.xml clean verify
bash scripts/start_business_backend.sh

# 另一终端，激活原 AI 环境
conda activate deer
pip install -r worker/requirements.txt
bash scripts/start_ai_worker.sh

# 前端开发：business 模式代理本机 6020
cd frontend
npm ci
npm run dev -- --mode business
```

Windows 本地只看前端时，通过 VS Code 转发云端 6020，再运行 Vite business 模式；只访问云端完整页面则转发 6010 即可。不要将内部 API 暴露到公网。

AutoDL 无 Docker daemon 时，在全新基础服务环境运行 `bash scripts/init_business_native.sh`（需预装 mysql-server、redis-server、rabbitmq-server；脚本自动生成未入库随机密码）。Redis 使用独立 6380。RabbitMQ 原生安装可用 `deploy/rabbitmq-business.conf` 绑定回环地址并提高长推理 ACK 超时，配置变更需重启新 RabbitMQ 服务。

静态部署：

```bash
# 构建可在本地完成，再上传 dist
cd frontend
npm run build -- --mode business
cd ..
install -d -m 755 /var/www/deer-business
cp -r frontend/dist/. /var/www/deer-business/
find /var/www/deer-business -type d -exec chmod 755 {} \;
find /var/www/deer-business -type f -exec chmod 644 {} \;
nginx -t -c "$PWD/deploy/nginx_business.conf"
nginx -c "$PWD/deploy/nginx_business.conf"
```

## 测试

```bash
mvn -f backend/pom.xml test
cd frontend
npm test
npx playwright test --config playwright.business.config.ts
cd ..
conda activate deer
bash scripts/test_business_native.sh
```

最后一条使用独立 MySQL `deer_business_test`、RabbitMQ vhost `deer_test`、API 6021、媒体 `/var/lib/deer-business-test`，验证真实 MySQL/Redis/RabbitMQ 和 Python 消费。测试会清理仅该测试 vhost 的队列；业务数据库与生产队列不动。推理使用显式 `--integration-test-double`，不等价于真实 GPU 模型测试。产物在 logs/business_verification.json、integration_worker.log、business_test_api.log。

生产 Worker 不应使用该测试开关。旧 SQLite 历史不会自动迁移进新 MySQL；旧页面仍能查看，新看板只统计新业务库。公开 API 延续项目无登录的单用户部署模式，只适合受信任的端口转发；公网部署前需要登录、租户隔离、配额与审计。

工程依据：[Spring Boot 3.5 Java 要求](https://docs.spring.io/spring-boot/3.5/system-requirements.html)、[RabbitMQ ACK/confirm](https://www.rabbitmq.com/docs/confirms)、[Dead-letter](https://www.rabbitmq.com/docs/3.13/dlx)。
