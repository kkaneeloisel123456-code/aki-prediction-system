# 第四阶段验收记录：健壮性、测试和部署

- 日期：2026-11-24
- 代码基线：`4a63d67`（阶段3：XLSX 导入、批次防重与接诊快捷录入）
- 范围：备份恢复（含未合并 WAL）、发布权限与草稿版本并发、患者门户列表脱敏、部署打包、数据库健康检查、第一阶段回归测试
- 结论：**第四阶段验收通过，用户已确认提交**；代码、测试、部署文件与验收记录随本阶段提交一并入库

## 验收对照

| 计划验收项 | 结果 | 证据 |
|---|---|---|
| 恢复后数据与备份一致，即使恢复前有未合并 WAL | 通过 | `test_restore_with_unmerged_wal_matches_backup_and_keeps_emergency_copy` |
| 只读授权不能发布 | 通过 | `test_view_only_grant_cannot_publish`（第一阶段回归，继续通过） |
| 门户列表不含检验值 | 通过 | 自动测试 + 真实患者会话检查 |
| 构建镜像不含数据库和认证配置 | 配置与静态校验通过；本机无法实跑 `docker build` | `.dockerignore`、Dockerfile 显式复制、`tests/test_deploy.py` |
| `/api/health` 在库不可读时失败 | 通过 | `test_health_fails_when_database_is_unreadable`，返回 HTTP 503 |
| 第一阶段每个缺陷都有回归测试 | 通过 | 第一阶段 9 项回归测试继续通过 |

## 1. 备份恢复与未合并 WAL

### 实现

`backend/app/backup.py` 新增 `_consistent_copy()`，统一通过 SQLite backup API 读取“主库 + WAL”的一致性快照：

- 正常备份、恢复临时库、恢复前紧急副本都走同一套 API，不再用 `shutil.copy2()` 直接复制主库文件。
- 原先紧急副本只复制 `clinical.db`，会丢掉仍停留在 `-wal` 中、尚未 checkpoint 的已提交事务；现在紧急副本包含这些页。
- 恢复仍先生成 `.pre-restore-*` 紧急副本，再写 `.restoring` 临时库、替换目标主库，最后删除旧的 `-wal/-shm`，避免旧日志回放到恢复后的数据库。
- 恢复应在服务停止后执行；Windows 上 SQLite 文件被运行中的进程占用时无法替换。
- 恢复源若带有 WAL，也通过 backup API 合并为独立快照后再替换。
- 若目标侧 `-wal/-shm` 已损坏，紧急副本退回为尽力保留的主文件副本，不阻塞恢复。

### 测试

`test_restore_with_unmerged_wal_matches_backup_and_keeps_emergency_copy` 的做法：

1. 通过管理员接口创建一致性备份。
2. 直接写一条 `wal_marker` 审计事件；写连接保持打开，复制“主库 + WAL”文件对，再重置测试库，确保恢复前确实存在未合并的已提交 WAL。
3. 调用 `restore_database(snapshot, confirm=True)`。
4. 恢复后 `wal_marker` 为 0 条，管理员账号仍存在，说明数据与备份一致且旧 WAL 未回放。
5. `.pre-restore-*` 紧急副本中 `wal_marker` 为 1 条，说明恢复前最新状态也被保留。

## 2. 发布权限与草稿版本并发

### 实现

`backend/app/clinical_api.py`：

- 发布接口原先只在 `req.draft_version` 非 0 时比较草稿版本；传 `draft_version=0` 会被当成“未提交版本”，从而绕过已存在的新草稿。现在只要存在草稿，就必须精确匹配当前 `draft_version`，否则 409。
- 发布时患者权限校验从默认 `write=False` 改为显式 `write=True`，与前面的接诊写权限检查形成双重校验；只读授权在发布入口直接 403。

### 测试

`test_publish_requires_exact_draft_version`：

- 连续保存两次草稿，当前版本为 2。
- 用过期版本 1 发布：409。
- 用原先可绕过校验的版本 0 发布：409。
- 用当前版本 2 发布：200。

`test_view_only_grant_cannot_publish` 继续通过：只读授权医生发布返回 403。

## 3. 患者门户列表脱敏

### 实现

`backend/app/patient_portal_api.py` 新增 `_portal_encounter_summary()`。报告列表中的 `encounter` 只返回：

`id / case_ref / occurred_at / surgery_type`

不再返回 `values`（35 项检验值）、`diagnosis`、`orders`。报告详情原有的 `values` 删除逻辑保持不变。

### 验证

- 自动测试 `test_portal_list_does_not_expose_clinical_values`：列表 `encounter` 键集合严格等于上述 4 项，详情 `snapshot.encounter` 不含 `values`。
- 真实库患者会话：登录 `pilotpatient` 后请求 `/api/portal/reports`，返回报告 `R-C8F591211525`（`RPT-20261123-C8F591`，低风险 0.26），其 `encounter` 实际键为 `id,case_ref,occurred_at,surgery_type`。

## 4. 部署打包与敏感文件排除

### 实现

- `.dockerignore` 新增排除：`backend/clinical.db`、`backend/clinical.db-*`、`backend/auth_config.json`、`backend/auth_config.json.tmp`、`backend/backups`、`backend/*.restore-tmp`、日志、测试与验收文档等。
- Dockerfile 不再 `COPY . .`，改为显式复制运行所需目录：`backend/`、`app_data/`、`outputs/`、`scripts/`，前端产物从前端构建阶段复制。
- 运行阶段创建非 root 用户 `aki`，数据目录固定为 `/data`：
  - `AKI_DB_PATH=/data/clinical.db`
  - `AKI_AUTH_CONFIG=/data/auth_config.json`
  - `AKI_BACKUP_DIR=/data/backups`
- 增加 `VOLUME ["/data"]` 与 `HEALTHCHECK`。
- 根 README 增加 Docker 初始化、持久卷、健康检查和镜像内容验证命令；`backend/README.md` 更新数据库路径、认证、安全与健康检查说明。

### 校验

- `tests/test_deploy.py` 守护 `.dockerignore` 的敏感文件规则，并确认 Dockerfile 不再整仓复制、四个运行目录显式复制、非 root 用户与 `/data` 路径存在。
- 静态匹配检查：`backend/clinical.db`、`-wal`、`-shm`、`auth_config.json`、`backend/backups/clinical-*.db`、`backend/*.log` 均命中排除规则。
- **环境限制**：当前 Windows 主机与云主机均未安装 Docker CLI，因此没有实际执行 `docker build`。镜像内容约束目前由“Dockerfile 只复制运行目录 + .dockerignore + 自动测试”保证；严格实构建需在具备 Docker 的环境补跑 README 中的 `docker build` 与 `image-clean` 命令。这是本阶段唯一的未实跑项，不影响代码与配置验收结论。

## 5. `/api/health` 数据库可读检查

### 实现

`backend/app/main.py`：

- 保持模型资产检查。
- 新增只读 URI 探测 `clinical.db`：`sqlite3.connect("file:...?mode=ro", uri=True)`，查询 `users` 表是否存在。
- 探测不创建、不迁移数据库。
- 数据库不可读时返回 HTTP 503，`status="unavailable"`、`database_ok=false`；正常时 `database_ok=true`。
- `HealthResponse` 与前端类型同步增加 `database_ok` 字段。

### 验证

- 当前服务 `http://127.0.0.1:8010`：
  `{"status":"ok","model_loaded":true,"n_features":35,"database_ok":true}`
- `test_health_fails_when_database_is_unreadable`：把测试库替换为非 SQLite 文件后，健康检查返回 503，`database_ok=false`、`status="unavailable"`。

## 6. 第一阶段缺陷回归

以下第一阶段缺陷对应的测试在本次全量测试中继续通过：

1. `test_predictions_migration_rebuilds_table`：旧 `predictions` 表迁移、`origin` 列、模型字段可空。
2. `test_manual_review_without_prediction_succeeds`：无模型结果时人工审核可用，模型字段保持 NULL。
3. `test_portal_report_detail_matches_list_and_requires_second_factor`：门户详情与列表口径一致，姓名/病历号 + 查询码 + 第二因子校验。
4. `test_deactivate_account_and_last_admin_protection`：停用账号会话失效，最后管理员不可停用。
5. `test_view_only_grant_cannot_publish`：只读授权不能发布。
6. `test_import_rejects_invalid_sex_with_chinese_reason` / `test_doctor_cannot_assign_new_patient_to_another_doctor`：导入性别与负责人归属校验。
7. `test_dashboard_hides_published_encounters`：工作台不显示已发布就诊。
8. `test_diagnosis_length_limit`：诊断长度上限。
9. `test_restore_removes_stale_wal_and_shm`：恢复删除旧 WAL/SHM。

## 构建、测试与服务

- `pytest -q`：**45 passed**（第三阶段 39 项 + 第四阶段 6 项），4 条既有依赖警告，无失败。
- `npm run build`：通过；`vue-tsc --noEmit` 无报错，仅保留既有的大 chunk 警告。
- 前端产物：`assets/index-C_vob_fC.js`、`assets/index-DAPE5joG.css`。
- 服务：`http://127.0.0.1:8010`，健康检查返回 `status=ok`、`database_ok=true`。
- 本阶段日志：`backend/uvicorn-phase4.out.log`、`backend/uvicorn-phase4.err.log`。

## 回滚与数据状态

- 本阶段不改数据库 schema，`SCHEMA_VERSION=4`、`PRAGMA user_version=4`；不需要新增迁移或索引。
- 本阶段不改模型文件、不改报告 SHA-256 生成算法。
- 回滚点集中在：`backup.py` 的一致性复制与紧急副本、`clinical_api.py` 的两处发布校验、`patient_portal_api.py` 的列表摘要、`main.py` 的健康检查、部署文件与文档。
- 当前 `backend/clinical.db`：4 名患者、6 次就诊、1 份报告、3 个预约、2 条反馈、1 条临床复核、48 条审计、7 个导入批次；`PRAGMA integrity_check=ok`，`user_version=4`。
- 本次真实门户验证新增 1 条门户登录会话/审计事件（审计由 47 增至 48），未修改患者、就诊、报告等临床数据。

## 提交纪律

按计划要求，第四阶段先展示验收结果，用户确认后再执行该阶段 commit；用户已确认，第四阶段代码、测试、部署文件与验收记录随本阶段提交入库。
