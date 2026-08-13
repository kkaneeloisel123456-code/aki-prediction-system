# 📦 app_data 目录说明

部署工件目录。FastAPI 后端启动时从这里加载模型，**这些文件随提交包一起分发**（非 Git-LFS 指针），评委解压即可运行。

## 文件清单

| 文件名 | 作用 |
|--------|------|
| `final_model.joblib` | 训练好的最终 Voting Ensemble（LR×2 + RF×2 + XGB×1 + ET×1），50 次嵌套 CV AUC 0.8096 ± 0.0428 |
| `scaler.joblib` | `StandardScaler`，把输入特征缩放到训练时的尺度 |
| `calibrator.joblib` | `IsotonicRegression` 校准器（基于 5 折 OOF 概率拟合），把原始概率校准到可解释水平 |
| `features.txt` | 模型使用的 35 个特征名，每行一个（顺序即模型输入顺序） |
| `impute_values.json` | 每个特征的训练集中位数；预测时缺失字段用它填补 |

后端加载逻辑见 [backend/app/assets.py](../backend/app/assets.py) 的 `load_assets()`。启动时会校验 `features.txt` 中的每个特征在 `impute_values.json` 中都有中位数，缺失则直接报错（fail-fast）。

## 与 `models/` 的关系

```
models/         训练产物（.pkl），走 Git LFS —— 用于训练溯源
app_data/       部署副本（.joblib/.txt/.json），普通 Git 文件 —— 后端实际加载
```

两套文件内容等价，区别只是存储格式与分发方式：

- `.pkl` 走 Git LFS，浅克隆/未装 LFS 时只有 100 多字节的指针文件，不可用；
- `.joblib` 是普通 Git blob，`git clone` 后立即可用，因此部署只依赖 `app_data/`。

## 重新训练后如何更新

运行 `python run_clean.py` 会在保存 `models/*.pkl` 的同时自动写入新的 `app_data/`（见 `src/data/prepare.py` 的 `save_app_data()`）。确认指标无回退后，`git add app_data/ && git commit` 即可。

## 手动从 models/ 转换（仅脚本未自动更新时）

```python
import pickle, joblib, shutil

with open('models/final_voting_model.pkl', 'rb') as f:
    joblib.dump(pickle.load(f), 'app_data/final_model.joblib')
with open('models/calibrator.pkl', 'rb') as f:
    joblib.dump(pickle.load(f), 'app_data/calibrator.joblib')
with open('models/scaler.pkl', 'rb') as f:
    joblib.dump(pickle.load(f), 'app_data/scaler.joblib')
shutil.copy('models/selected_features.txt', 'app_data/features.txt')
# impute_values.json 由 run_clean.py 在训练时直接写出，无需从 pkl 转换
```
