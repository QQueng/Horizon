# Fork 部署准备

仓库：`QQueng/Horizon`（fork 自 `Thysrael/Horizon`）。

这份准备只提交配置和工作流。日报没有运行，也没有发布。

## 配置来源

`data/config.deploy.json` 来自官方 GitHub Actions 示例 `data/config.github.json`。

其中的模型、语言和信息源是上游模板自带的样本，用来让配置能够通过校验。模型服务、密钥、关注主题和是否公开日报都还没有选定。

相对该官方示例，只做了两处安全收紧：

- `webhook.enabled` 为 `false`
- 带有 `${LWN_KEY}` 的 LWN.net 源为 `enabled: false`

上游模板文件 `.github/workflows/daily-summary.yml.disabled` 保持原样，作为官方参考。

## 开关

| 项目 | 状态 |
| --- | --- |
| 定时任务 | 关闭。`daily-summary.yml` 只有手动 `workflow_dispatch` |
| GitHub Pages | 关闭。工作流不发布、不推送页面 |
| 邮件、Webhook、微信 | 关闭。运行环境不接收 Webhook 地址 |
| 默认手动运行 | 只检查配置 |
| 调用模型 | 检查通过，并且手动打开 `run_pipeline` 之后才会执行 |

合并到默认分支之后，可以在 Actions 里手动运行 “Horizon manual run”。未设置必需 secret 时，检查步骤会失败并打印变量名，到此停止。默认不勾选 `run_pipeline` 时，即使 secret 已经存在，也只做检查。

打开 `run_pipeline` 后，生成的文件只留在 runner 上，作业结束即丢弃。工作流不上传 artifact，不把日报提交回仓库。公开仓库的 Actions 日志仍可能显示命令输出；第一次真正运行前需要接受这一点，或先调整仓库可见性。

`deploy-docs.yml` 仍是上游原文件。这次改动不包含它的触发路径，因此合并这次改动不会发布 Pages。

## 调用模型前需要的 secret

当前这份配置要求：

- `DEEPSEEK_API_KEY`

在仓库的 Settings → Secrets and variables → Actions 中添加该名称。把密钥写在 secret 里，不要写进仓库文件。

工作流还会把官方模板里的其他模型变量名传给检查步骤，供以后改配置时识别。当前示例不要求它们：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT`、`MINIMAX_API_KEY`、`DASHSCOPE_API_KEY`、`DOUBAO_API_KEY`、`LWN_KEY`。

Actions 会自动提供 `GITHUB_TOKEN`。不需要另建同名 secret。

## 继续之前还需要的选择

- 实际要使用的模型服务。当前 DeepSeek 与 `deepseek-v4-flash` 是官方示例。
- 该服务的 API 密钥，对应上表中的 secret 名称；若改了 `ai.api_key_env`，secret 名称跟着改。
- 关注的信息源。当前来源列表是官方示例。
- 是否公开日报，以及是否启用 Pages。
- 是否定时运行；若要定时，需要时区和本地时间。GitHub 的 cron 默认按 UTC 解释。
- 是否使用邮件、Webhook 或微信。启用发送需要另行打开配置，并让工作流传入对应 secret。
