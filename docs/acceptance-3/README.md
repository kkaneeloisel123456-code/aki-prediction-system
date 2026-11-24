# 第三阶段验收记录：Excel 和日常录入

- 日期：2026-11-24
- 代码基线：`3e5ca67`（阶段 2b：模型说明、数据治理与患者门户统一）
- 范围：XLSX/CSV 批量导入预览、工作表选择、列映射、批次提交、错误行导出、批次与文件防重；接诊页复制上次就诊、粘贴表格填指标
- 结论：**第三阶段验收通过，用户已确认提交**；保留 2 条非阻塞观察项（见文末）

## 构建、测试与服务

- `npm run build` 通过，`vue-tsc --noEmit` 无报错，仅保留既有的大 chunk 警告。
- `pytest -q`：**39 passed**，含第三阶段新增的 5 个导入测试。
- 当前产物：`assets/index-C_vob_fC.js`、`assets/index-DAPE5joG.css`；首页已引用这两个文件。
- 服务：`http://127.0.0.1:8010`。
- 健康检查：`{"status":"ok","model_loaded":true,"n_features":35}`。
- 本阶段日志：`backend/uvicorn-phase3b.out.log`、`backend/uvicorn-phase3b.err.log`。

## 数据库与回滚点

- `SCHEMA_VERSION=4`，`PRAGMA user_version=4`。
- 迁移前备份：`backend/backups/clinical-before-phase3-20261124-142457.db`。
- `import_batches` 新增 `preview_json`、`mapping_json`、`file_hash`、`sheet_name`、`updated_at`；索引 `idx_import_batches_hash` 在加列之后创建。
- 迁移未改写既有患者、就诊、报告与原有导入批次。
- 实现期间修复两处实际缺陷：
  1. Excel 日期序列号经规范化后成为数字字符串，`_parse_dt` 原先只识别数值类型；现已支持数字字符串按 Excel serial 解析。
  2. `_SCHEMA` 在旧表上提前创建 `file_hash` 索引，导致旧库启动时报 `no such column: file_hash`；索引已移入 `_migrate_import_batches_v4`，先加列再建索引。

## 批量导入验收

### 模板、工作表与映射

- `GET /api/imports/template.xlsx` 可下载，工作表“导入模板”含患者字段、就诊字段、负责人 ID 与 35 项特征；旧 `GET /api/imports/template.csv` 仍保留。
- 上传 `phase3-ui-two-sheets.xlsx` 后，页面出现“导入数据 / 错误示例”工作表选择；未选择工作表时不创建批次。
- 首次预览因“病历编号 / 患者姓名”未自动识别，出现有效行 0、错误行 2；在映射弹窗分别改为 `mrn`、`name` 后重新校验，有效行 2、错误行 0。
- 随后补充 `病历编号 → mrn`、`患者姓名 → name`、`病案号 → mrn`、`病人姓名 → name` 等常见别名；用 `phase3-ui-alias.xlsx` 复测，9 列全部自动映射，有效行 1、错误行 0。见 `phase3-batch-alias-automap-1280.png`。
- 列映射弹窗按“患者信息 / 就诊信息 / 模型指标”分组，可逐列调整；表头重复、空列、映射到未知字段、多列映射同一字段、缺少必需列会形成 `header_errors`，前端禁止提交。

### 批次提交与防重

- 新页面提交只发送 `batch_id`，不信任前端回传行数据；旧 `{filename, rows}` 路径完整保留一版，旧测试和旧客户端仍可使用。
- 批次 `IMP-A93DB7A55B79`（`phase3-ui-two-sheets.xlsx` / 导入数据）提交成功 2 行，新建患者：
  - `P-942686A11601`（UI-P3-001 / 阶段三验收甲 / UI-CASE-001 / `E-406DE9A789B3`）
  - `P-5524548E64DF`（UI-P3-002 / 阶段三验收乙 / UI-CASE-002 / `E-EED73C1516D3`）
- 再次选择同一文件时，页面提示“该文件已导入过（批次 IMP-A93DB7A55B79），不能重复提交”。见 `phase3-batch-duplicate-file-1280.png`。
- 接口层同时覆盖：同一批次重复提交 409、同一文件哈希已有 completed 批次时拒绝预览；提交事务内再次检查批次状态与文件哈希。
- 提交使用单个 `BEGIN IMMEDIATE` 事务，每行一个 SAVEPOINT；行级失败仅回滚该行，批次最终统一写 `completed`。

### 错误行与导出

- `phase3-ui-errors.xlsx` 预览有效行 0、错误行 3；错误包括错误性别、同一文件内病历号重复且姓名不一致、术前 Scr=99999 超出临床合理范围。
- 页面“导出错误行”按钮触发 `GET /api/imports/{batch_id}/errors.xlsx`，后端返回 200。
- 直接取回的错误工作簿为 5624 bytes、工作表“错误行”4 行（1 表头 + 3 错误行），表头为 `行号 / 错误 / 提示 / 病历号 / 姓名 / 性别 / 出生年份 / 就诊编号 / 发生时间 / 负责人ID / 术前Scr / 术前eGFR`，仅导出有错误的行，并保留原始源列。
- 对应批次：`IMP-D42376B15657`、`IMP-C06A69F1649A`（均为 preview，未提交）。见 `phase3-batch-errors-1280.png`。

## 接诊页验收

- 导入的 `E-406DE9A789B3` 打开后显示“2 项实测 / 35 项”，术前肌酐 88、术前 eGFR 92 正常回填，不再出现导入值只在库里、页面为空的脱节。见 `phase3-encounter-imported-summary-1280.png`、`phase3-encounter-imported-values-1280.png`。
- 为同一患者 `P-942686A11601` 新建空就诊 `E-70B3E236D209`（CASE-20261124-002），接诊页自动识别“上次 UI-CASE-001 · 2026/11/20 00:00”。
- 点击“复制上次就诊”后填入 2 项指标，页面提示“已从上次就诊填入 2 项指标”。见 `phase3-encounter-copy-last-1280.png`。
- 再次验证只补空项：先手工填术前肌酐 77，再复制上次就诊，页面提示“已从上次就诊填入 1 项指标，保留 1 项已填值”。见 `phase3-encounter-copy-preserve-1280.png`。
- “粘贴表格”支持两列（指标名 + 数值）或一行表头 + 一行数值，可带单位；本次粘贴术前收缩压 130、术前白细胞 6.2、APACHE II 评分 10、术后乳酸 1.2，弹窗识别“填入 4 项”，应用后指标区计数由 0 变为 4。见 `phase3-encounter-paste-table-1280.png`。
- 未识别指标名会列在弹窗中；勾选“覆盖当前已填写的指标”后才覆盖已有值，默认只补空项。

## 多工作表、CSV 与权限回归

- XLSX fixture `tests/fixtures/phase3_two_sheets.xlsx` 覆盖合并单元格向下填充、Excel 日期序列号、科学计数法、多工作表、错误性别、重复病历号。
- GBK CSV fixture `tests/fixtures/phase3_gbk.csv` 预览 2 行有效并可按批次提交；CSV 保留 UTF-8 BOM 与 GB18030 解码。
- 医生导入新患者时 `owner_id` 只能是本人 ID 或用户名；管理员必须显式填写有效医生，预览阶段即校验。越权归属测试返回拒绝。

## 截图索引（1280）

| 场景 | 文件 |
|---|---|
| 批量导入入口 | `phase3-batch-upload-1280.png` |
| 双工作表选择 | `phase3-batch-sheet-choice-1280.png` |
| 手工修正映射后的批次预览 | `phase3-batch-mapping-preview-1280.png` |
| 批次提交完成 | `phase3-batch-commit-1280.png` |
| 别名自动映射 | `phase3-batch-alias-automap-1280.png` |
| 同一文件重复导入拦截 | `phase3-batch-duplicate-file-1280.png` |
| 错误行预览与导出按钮 | `phase3-batch-errors-1280.png` |
| 导入指标回填摘要 | `phase3-encounter-imported-summary-1280.png` |
| 导入指标回填明细 | `phase3-encounter-imported-values-1280.png` |
| 复制上次就诊 | `phase3-encounter-copy-last-1280.png` |
| 复制不覆盖已填值 | `phase3-encounter-copy-preserve-1280.png` |
| 粘贴表格填指标 | `phase3-encounter-paste-table-1280.png` |

本阶段验收页面以桌面录入为主，截图宽度为 1280；未另行补 1440/1920/390 矩阵。第三阶段计划未要求多宽度截图。

## 保留观察项

1. **Browser Use 自动下载未落盘，但 Tabbit 真实下载可用**：点击“导出错误行”后，后端日志确认 `GET /api/imports/{batch_id}/errors.xlsx` 返回 200，但 Browser Use 的浏览器触发下载在 30 秒内未产生可记录文件；同一 URL 用 `bu.download()` 直接取回成功，文件 5624 bytes，工作簿内容与预期一致。补充验证：在 Tabbit 本机浏览器打开同款 `saveBlob` 下载测试页，物理点击后成功下载到 `D:\电脑\浏览器下载`，说明浏览器下载路径和 `saveBlob` 代码本身可用；未在 AKI 页面实际点击的唯一原因是 Tabbit 默认配置未登录，登录需用户本人输入。测试文件与临时页面已清理。
2. **SPA 地址与标题偶发不同步**：批量导入页实际内容为“批量导入”，`bu.current_tab()` 仍可能显示 `http://127.0.0.1:8010/`、标题“录入”；与 2b 已记录的自动化浏览器 URL 跟踪差异一致，页面路由与业务操作正常。

## 当前数据状态

`backend/clinical.db` 当前：4 名患者、6 次就诊、1 份报告、3 个预约、2 条反馈、1 条临床复核、47 条审计、7 个导入批次（2 个 completed、5 个 preview）。第三阶段验收新增 2 名患者、2 次导入草稿就诊和 1 次用于验证“复制上次就诊”的空就诊；5 个 preview 批次包括 3 个错误文件预览、1 个别名映射预览和 1 个初始映射预览。未清理，保留用于本轮复现；进入下一阶段前可按需清空这批验收数据。

## 提交纪律

按计划要求，本阶段完成后先提交验收结果给用户查看；用户已确认，第三阶段代码、测试、fixture 与验收记录随本次提交一并入库。
