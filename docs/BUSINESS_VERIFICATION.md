# 验收记录（2026-09-18）

## 已实际执行

- 本地 Java 17 + Maven `clean verify`：成功，3 项 JPA/状态机测试通过。
- 云端 Java 17 + Maven `clean verify`：成功，同样 3 项测试通过。
- React TypeScript business 生产构建：成功。
- Playwright 旧 FastAPI 模式：5 项通过。
- Playwright Spring Boot 契约模式：1 项通过，含上传、字段适配、终态停止轮询、筛选和看板。
- 云端真实 MySQL 8.0.46、Redis、RabbitMQ 集成测试：通过。

## 真实基础设施证据

隔离数据库 deer_business_test、RabbitMQ vhost deer_test、API 6021。生产数据库没有测试数据。

验证了 Spring Boot 启动与四张表自动创建、Redis Hash 写入及终态 TTL、RabbitMQ 发布确认与消费、手动 ACK、重复消息跳过、重复事件只保留一行、非法流转 409、内部鉴权 401、视频 Range 206、统计和筛选查询。

| 测试任务 | 最终状态 | 执行次数 | 事件数 |
|---|---|---|---|
| 8c3f52c5-e80c-4448-a058-b835df862647（内部接口测试） | COMPLETED | 1 | 1 |
| 6f073e25-4c31-49ea-9cff-09a79954bc0d（Worker 消费测试） | COMPLETED | 1 | 1 |
| 19459150-c772-427f-9797-b20d9f00ab6e（故意失败） | FAILED + DLQ | 4 | 0 |

正常任务再次投递两条相同消息后 attempts 仍为 1；失败任务首次执行加 3 次重试后进入 DLQ。RabbitMQ Management 查询主队列 messages_unacknowledged=0、messages_ready=0。

云端日志：logs/business_build.log、logs/business_integration.log、logs/integration_worker.log、logs/business_verification.json。可通过 scripts/test_business_native.sh 重新执行。

## 验证边界

云端当前为无 GPU 的 CPU 实例。推理在隔离测试中使用显式 integration-test-double，因此没有声称本次完成真实 YOLO/Qwen GPU 推理验收。正式 Worker 使用原 pipeline，不启用测试替身。需要启用 GPU 后再上传真实视频做模型端到端验收。

旧 SQLite 历史没有迁移到新 MySQL；6008/6009 保留旧部署，新业务版使用 6010。没有替换原模型算法，没有清除旧视频或数据库。
