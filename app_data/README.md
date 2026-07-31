# 📦 app_data 目录说明

> 写给零基础组员 —— 这个文件夹是干什么的？怎么用？

---

## 1. 这个文件夹里有什么？

| 文件名 | 大小 | 作用 |
|--------|------|------|
| `final_model.joblib` | ~几MB | 训练好的**最终模型**（Voting Ensemble，AUC 0.821） |
| `scaler.joblib` | 小 | **数据标准化器**，把新数据缩放到和训练时一样的尺度 |
| `features.txt` | 小 | 模型用的 **35 个特征名**列表 |

---

## 2. 为什么要有这个文件夹？

### 一句话解释：**GitHub 不让直接上传大文件，所以我们在 models/ 和 app_data/ 各放一份。**

具体原因：

```
models/  里的 .pkl 文件 → 用了 Git LFS（大文件存储），Streamlit Cloud 读不了 ❌
app_data/ 里的 .joblib 文件 → 普通 Git 文件（与 LFS 无关），Streamlit Cloud 能读 ✅
```

> 💡 **Git LFS** = GitHub 的大文件管理功能。免费仓库单文件不能超过 100MB，但模型文件很大，所以 GitHub 自动把大文件存到 LFS。问题是 Streamlit Cloud 不支持 LFS，所以我们手动在 `app_data/` 里用小格式（.joblib）再存一份。

---

## 3. 组员需要做什么？

### 场景一：你只是运行 Streamlit 网页

**什么都不用做。** 代码会自动从 `app_data/` 读取模型。

### 场景二：你本地跑 streamlit_app.py 发现没有模型文件

你需要把模型文件放到 `app_data/`：

**步骤：**

1. 去 GitHub 仓库的 `app_data/` 目录
2. 点击三个文件，一个一个 **下载（Download）**
3. 下载后放到你电脑上 `aki-project/app_data/` 文件夹里

> ⚠️ 注意：这三个文件**不是 Git LFS 文件**，直接从 GitHub 网页下载就行，不需要装 Git LFS。

### 场景三：你重新训练了模型，想更新 app_data/

运行训练脚本后，在 Python 里执行：

```python
import joblib
import pickle

# 1. 把 .pkl 转成 .joblib（更小更快）
with open('models/final_voting_model.pkl', 'rb') as f:
    model = pickle.load(f)
joblib.dump(model, 'app_data/final_model.joblib')

# 2. 复制 scaler
with open('models/scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)
joblib.dump(scaler, 'app_data/scaler.joblib')

# 3. features.txt 直接复制粘贴就行
```

然后 `git add app_data/` → `git commit` → `git push` 即可。

---

## 4. 常见问题

**Q: 为什么不用 Git LFS 统一管理？**
A: LFS 免费额度有限（1GB 存储 + 1GB 带宽/月），而且 Streamlit Cloud 不支持 LFS。

**Q: .joblib 和 .pkl 有什么区别？**
A: 都是存模型的文件格式。`.joblib` 压缩率更高、加载更快，适合部署；`.pkl` 是 Python 原生格式，兼容性最好。

**Q: 模型更新后，app_data 和 models 都要更新吗？**
A: 对。`models/` 是训练产物（存原始 .pkl），`app_data/` 是部署用的副本（转成 .joblib）。

---

## 5. GitHub 上怎么下载文件？

1. 打开仓库页面：`https://github.com/你的用户名/aki-project`
2. 点进 `app_data/` 文件夹
3. 点某个文件 → 点右上角 **"Download raw file"** 按钮（或右键 → 另存为）
4. 把三个文件都下载到本地 `app_data/` 文件夹
