# 阿里云按正式 Release 自动部署

适配当前 Ubuntu + Nginx + Docker 单机部署。生产容器为 `aki-system`，只绑定
`127.0.0.1:8000`，业务数据在 `aki-data:/data`。现有管理员、医生、患者和报告不重新初始化。

## 运行方式

- systemd 每 10 分钟（另加最多 30 秒错峰）检查 GitHub Releases API 的最新正式版。
- 只接受已经发布且非预发布的 `vX.Y.Z` 标签。只推送 `main` 不触发上线。
- 单进程锁防止重复部署；相同版本不构建、不重启；API 连接失败保留当前服务。
- 标签固定到完整 Git commit；已见标签不允许强制移动，旧版和分叉版本拒绝覆盖新版。
- 在独立 checkout 构建 Docker 镜像。Python 3.12，模型依赖固定为
  `scikit-learn==1.9.0`、`xgboost==3.3.0`，避免之前的序列化版本不匹配。
- 用线上数据库的一致性副本在隔离的数据卷启动候选容器。验证 `/api/health`、
  `/openapi.json`、前端首页及 JavaScript 资源，然后才切换正式服务。
- 切换时 Nginx 暂时返回 503。停止旧服务后用 SQLite backup API 再生成最终快照，
  校验完整性与 SHA-256，再让新版本使用原数据卷启动。
- 新版验证失败自动停用新版、恢复快照、启动原容器；确认旧版健康后才恢复访问。
  回滚也失败时保持维护状态并在 journal 报错，避免放出故障服务。
- 持久化事务日志支持部署进程中断后的恢复。成功后保留最近 5 份发布快照、
  最近 2 份预检快照；应用自身备份和故障恢复副本不清理。
- 同一失败版本默认冷却一小时；修复后可用 `--retry` 主动重试。

构建期间原服务持续运行；最终切换会有一段维护时间。预检过程中不调用真实患者的
预测、复核或发布操作。回滚快照覆盖切换时点之前的数据，维护门禁用于防止切换窗口
内继续写入。数据库与账号密钥保留在原服务器数据卷，不进入 GitHub 或镜像。

## 首次安装

从本仓库取得代码后，在服务器上执行：

```bash
sudo bash deploy/install.sh /etc/nginx/conf.d/aki.conf
sudo cat /etc/aki-deploy.json
sudo systemctl start aki-release.service
sudo journalctl -u aki-release.service -n 60 --no-pager
sudo /opt/aki-deploy/deploy.sh --status
sudo systemctl enable --now aki-release.timer
sudo systemctl list-timers aki-release.timer
```

安装器保留现有 Nginx 配置，只增加维护门禁 include，并在语法检查失败时恢复原配置。
已有 `/etc/aki-deploy.json` 不覆盖。首次部署成功前不启用 timer。

程序安装在 `/opt/aki-deploy`，状态、构建日志与独立源码 checkout 在
`/var/lib/aki-deploy`；数据库发布快照在数据卷 `/data/deploy-backups/`。
正式容器之外的预检数据卷只用于验证，验证后删除。旧容器保留为 `aki-rollback-*`；
失败容器停用自动重启并保留为 `aki-failed-*`，便于排查。
旧镜像、旧容器和源码 checkout 暂不自动删除，运维需留意磁盘空间。

## 日常操作

```bash
# 查看当前正式版本
sudo /opt/aki-deploy/deploy.sh --status
# 立刻检查最新正式版
sudo systemctl start aki-release.service
# 日志与定时器
sudo journalctl -u aki-release.service -n 80 --no-pager
sudo systemctl status aki-release.timer --no-pager
# 明确重试一个失败版本（与定时任务共享同一把锁）
sudo /opt/aki-deploy/deploy.sh --tag v1.1.2 --retry
# 暂停后续自动更新，当前网站继续运行
sudo systemctl disable --now aki-release.timer
```

候选镜像构建日志为 `/var/lib/aki-deploy/build-vX.Y.Z.log`。GitHub API 无需令牌，
服务器无需接收入站 webhook，也无需把 SSH 私钥放进 GitHub。发布者仍需测试并
发布正式 Release；不要移动已经发布的标签。仅发布 `main` 的后续版本。
自动更新程序本身不会随应用 Release 自动替换；修改部署工具后需重新运行安装器。

## 本地验证范围

部署事务、版本处理、故障恢复、SQLite WAL/校验与保留策略的 29 项测试通过；
连同账号、注册、核心业务与打包回归，共 82 项通过。现有本机模型库版本警告仍存在，
云端构建通过固定模型依赖避免该版本差异。两个科研训练测试模块需额外安装
`optuna` / `imbalanced-learn`，未包含在本轮执行范围。服务器安装后的实际 Docker
构建、Nginx 维护门禁、定时器和公网验证仍需在服务器上执行，不能由本地模拟测试替代。

## 人工恢复

部署中的自动恢复依赖 `transaction.json` 和保留的旧容器。若自动恢复报错，先停止
timer，保持 `/var/lib/aki-deploy/maintenance`，查看日志与 `transaction.json`，确认
旧容器、快照及数据卷存在。修复环境问题后重新运行 `deploy.sh` 会先恢复未完成的
事务。不要删库、创建新数据卷或重新运行账号初始化来解决发布故障。

当前访问方式仍沿用现有 Nginx；本工具不新增公网端口或改变域名配置。
