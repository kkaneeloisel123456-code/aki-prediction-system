# AKI Prediction Backend

FastAPI 服务，封装已训练的 Voting Ensemble，供 Vue 前端调用。

## 运行

```bash
# 项目根目录下
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt

# 启动 API（自动托管 frontend/dist 下的前端构建产物）
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- API 文档（Swagger UI）：<http://localhost:8000/docs>
- 前端开发模式（热重载）：另开终端进入 `frontend` 目录后运行 `npm run dev`，访问 <http://localhost:5173> ，Vite 会把 `/api` 代理到 8000
- 生产模式：先在 `frontend` 目录执行 `npm install` 和 `npm run build`，再启动后端，浏览器直接访问 <http://localhost:8000> 即可拿到前端页面
- 容器部署：在项目根目录执行 `docker build -t aki-prediction-system .`，运行时把 `/data` 挂载为持久卷；镜像内的数据库路径为 `/data/clinical.db`，认证配置为 `/data/auth_config.json`，备份目录为 `/data/backups`。完整初始化命令见根目录 README「方式三：Docker」。

启动时后端从项目根的 `app_data/` 加载模型工件（`final_model.joblib`、`scaler.joblib`、`calibrator.joblib`、`features.txt`、`impute_values.json`）。工件缺失会在启动阶段直接失败（fail-fast），而不是在第一次预测时才报错。

## 预测流程

```text
POST /api/predict  { features: {特征名: 数值, ...}, patient_id? }
  → 按 features.txt 组装 35 维向量（缺失值用训练集中位数填补，NaN/Inf/非数值同样视为缺失）
  → StandardScaler 变换
  → Voting Ensemble.predict_proba  (LR×2 + RF×2 + XGB×1 + ET×1)
  → IsotonicRegression 校准（基于 5 折 OOF 概率拟合），裁剪到 [0, 1]
  → 风险分层：<0.30 低 / 0.30–0.70 中 / ≥0.70 高
  → 可选 SHAP 解释（基于 XGBoost 子模型，TreeExplainer）
  → PredictResponse
```

SHAP 使用从 Voting Ensemble 中取出的 XGBoost 子估计器，因此即使 `models/*.pkl` 是未拉取的 Git-LFS 指针也不受影响。

## 端点

| 方法 | 路径 | 用途 |
| ---- | ---- | ---- |
| GET | `/api/health` | 服务、模型与数据库可读状态；任一依赖不可用时返回 HTTP 503，JSON 中 `database_ok=false` 表示 `clinical.db` 无法读取 |
| GET | `/api/meta` | 首页元数据（特征数、模型数、best_auc、风险阈值） |
| GET | `/api/features` | 35 个特征名 + 中文标签/单位/参考范围/中位数/时点 |
| GET | `/api/data/imputation` | 每个特征的训练集中位数填充值 |
| GET | `/api/data/quality` | 训练队列数据质量统计（样本量/缺失率/分类平衡/类型分布） |
| POST | `/api/predict` | 单人预测：概率 + 风险等级 + SHAP |
| POST | `/api/predict/batch` | JSON 数组批量预测（返回 `patient_id`、概率、等级、二分类） |
| POST | `/api/predict/csv` | CSV 上传 → 逐行预测 → CSV 下载（支持 UTF-8 BOM，非数值单元格按缺失处理） |
| POST | `/api/report/pdf` | 生成单人 PDF 报告（fpdf2 + 内置 CJK 字体，内存返回） |
| GET | `/api/template.csv` | 下载 35 列 CSV 模板（含一行中位数示例） |
| GET | `/api/performance` | 模型性能指标（从 `outputs/tables/` 读取 CV/校准/HL 等 CSV） |
| GET | `/api/figures` | 列出可用图表文件名 |
| GET | `/api/figures/{name}` | 获取指定图表（PNG/JPG） |
| GET | `/api/tables` | 列出可用表格文件名 |
| GET | `/api/tables/{name}` | 获取表格（CSV 转 JSON，或原文） |
| GET | `/api/workstation/cohort` | 20 例合成患者队列（seed=42，真实模型预测，仅演示） |
| GET | `/api/dashboard/demo` | 管理仪表盘演示数据（硬编码，非真实科室统计） |
| GET | `/{path}` | 托管 `frontend/dist` 下的静态前端（SPA history 回退） |

## 配置

- **风险阈值**：`RISK_LOW = 0.30`、`RISK_HIGH = 0.70`（在 [config.py](app/config.py)，必须与 `src/config.py` 一致；由测试守护）
- **数据库与认证文件**：`AKI_DB_PATH` 覆盖 `backend/clinical.db`，`AKI_AUTH_CONFIG` 覆盖 `backend/auth_config.json`，`AKI_BACKUP_DIR` 覆盖 `backend/backups`。容器镜像默认全部放在 `/data`。
- **CORS**：默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`（Vite 开发服务器）。生产环境用环境变量 `CORS_ORIGINS` 追加来源（多来源逗号分隔），例如：

  ```bash
  set CORS_ORIGINS=https://your-domain.example.com
  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
  ```

  前后端同源部署时（后端直接托管 `frontend/dist`）不需要设置。
- **Cookie 安全**：HTTPS 部署设置 `AKI_AUTH_SECURE_COOKIE=1`；会话时长可用 `AKI_AUTH_SESSION_HOURS` / `AKI_AUTH_REMEMBER_DAYS` 调整。
- **PDF 中文字体**：按 `backend/assets/fonts/` → `C:/Windows/Fonts/` 的顺序查找 TTF；找不到 TTF 时抛出 RuntimeError（无法生成中文 PDF）（中文会无法显示）。

## 安全说明

- `/api/figures/{name}`、`/api/tables/{name}`、`/{path}` 都做了路径穿越防护，禁止访问基础目录之外的文件。
- 员工 API 使用数据库会话 Cookie、CSRF 双提交校验和基于患者归属/授权的 RBAC；患者门户使用独立 Cookie，不能调用员工业务 API。首次登录必须改密，会话可在管理员页面撤销。
- 患者数据库、WAL/SHM、认证配置和备份默认位于 `backend/`，已被 Git 与 `.dockerignore` 排除；容器部署请把 `AKI_DB_PATH`、`AKI_AUTH_CONFIG`、`AKI_BACKUP_DIR` 指向持久卷 `/data`。
- 生产环境应启用 HTTPS，并设置 `AKI_AUTH_SECURE_COOKIE=1`；系统应部署在受控内网或经医院批准的服务器上。
- 患者级数据不落盘日志；`patient_id` 在 Content-Disposition 文件名中会被净化为 `[A-Za-z0-9_.-]`。
