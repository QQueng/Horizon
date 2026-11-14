# Fork 部署

仓库：`QQueng/Horizon`。默认分支：`main`。

工作流文件：`.github/workflows/daily-summary.yml`。Actions 里的名称：`Horizon daily digest`。

日报在合并到 `main` 之后，才会按计划开始。合并之前不会每天运行。

## 时间

定时表达式是 UTC `0 0 * * *`。上海没有夏令时，这对应每天北京时间 08:00，含周六和周日。

GitHub Actions 的定时任务可以晚于设定时间才开始。这个配置不保证 08:00 准点生成，也不保证 08:00 已经送到聊天。

手动 `workflow_dispatch` 仍保留。`run_pipeline` 默认关闭时只做预检。定时触发不读取这个默认值：预检通过后会运行日报流水线。预检失败则不会调用模型，也不会上传日报。

## 模型

提供方是 DeepSeek。模型标识使用官方当前名称 `deepseek-flash`，对应文档中的 DeepSeek-V4.1-Flash-1017。

依据是 DeepSeek 公开文档，没有调用 API：

- https://api-docs.deepseek.com/ 将 `model` 列为 `deepseek-flash` 与 `deepseek-v4-pro`，并写明使用 `deepseek-flash` 作为模型名。
- https://api-docs.deepseek.com/quick_start/pricing/ 写明 `deepseek-v4-flash` 是仍被接受的旧名，对应模型已退役，请求由 DeepSeek-V4.1-Flash-1017 提供并按 Flash 价格计费。
- https://api-docs.deepseek.com/guides/thinking_mode 写明思考模式默认开启。配置里的 `ai.extra_body.thinking.type` 为 `disabled`，让每日摘要走非思考模式。这是可调整项。

接口地址是 `https://api.deepseek.com`。密钥只从名为 `DEEPSEEK_API_KEY` 的 Actions secret 读入。仓库文件不包含密钥值。

定时运行和手动打开 `run_pipeline` 都会调用这个付费接口。只跑预检不会调用。

默认输出语言是中文（`ai.languages` 为 `zh`）。

## 四类上限

这些数字是上限，不是每天必须凑满的条数。分数低于 7 的条目不会为了凑满名额留下。某一类当天没有足够合格内容时，该类可以少于 5 条，整天也可以少于 20 条。

| 项目 | 可调整默认值 |
| --- | --- |
| 日报总量 `digest.max_items` | 20 |
| AI与科技 `ai-tech` | 5 |
| 财经与市场 `finance-markets` | 5 |
| 工程与建筑 `engineering-architecture` | 5 |
| 历史与人文 `history-humanities` | 5 |
| 未分类 `default_group_limit` | 1 |

抓取窗口是最近 24 小时。历史与人文只收录新发表研究、考古报道、博物馆与遗产动态。配置要求模型不要把古代故事改写成当天突发新闻。

2026-11-14 检查时，故宫、中国国家博物馆、国家文物局和中国考古网没有返回可用的公开 RSS。历史类因此使用下面核对过的公开源；中文文化源只作为人文入口，达不到分数就不会占名额。

## 已核对的来源

2026-11-14 用公开 HTTP 请求核对过：返回 RSS/Atom，且条目带有日期。

| 类别 | 名称 | 链接 |
| --- | --- | --- |
| AI与科技 | 量子位 | https://www.qbitai.com/feed |
| AI与科技 | 雷峰网 | https://www.leiphone.com/feed |
| AI与科技 | InfoQ 中文 | https://www.infoq.cn/feed |
| AI与科技 | MIT Technology Review | https://www.technologyreview.com/feed/ |
| 财经与市场 | 华尔街见闻 | https://dedicated.wallstreetcn.com/rss.xml |
| 财经与市场 | FT中文网 | https://www.ftchinese.com/rss/news |
| 财经与市场 | 经济观察网 | https://www.eeo.com.cn/rss.xml |
| 工程与建筑 | ArchDaily 中文 | https://www.archdaily.cn/cn/feed |
| 工程与建筑 | 建筑学院 | https://www.archcollege.com/feed |
| 工程与建筑 | Dezeen | https://www.dezeen.com/feed/ |
| 工程与建筑 | Engineering News-Record | https://www.enr.com/rss/articles |
| 历史与人文 | 中国新闻网文化 | https://www.chinanews.com.cn/rss/culture.xml |
| 历史与人文 | Archaeology Magazine | https://www.archaeology.org/feed/ |
| 历史与人文 | Science News Archaeology | https://www.sciencenews.org/topic/archaeology/feed |
| 历史与人文 | Nature Archaeology | https://www.nature.com/subjects/archaeology.rss |

## 产物

成功生成非空中文 Markdown 后，工作流把它复制为 `digest/horizon-zh.md`，再上传为 Actions artifact。

| 项 | 值 |
| --- | --- |
| 工作流名称 | `Horizon daily digest` |
| 默认分支 | `main` |
| artifact 名称 | `horizon-digest` |
| artifact 内路径 | `digest/horizon-zh.md` |
| 保留 | 7 天 |

失败、或没有生成非空中文日报时，不上传文件，也不写入占位日报。上传内容只有这一份 Markdown，不包含密钥、环境变量或 `.env`。

主助手可以用 GitHub 的普通 artifact 接口读取，例如列出某次运行的 artifacts，再下载 zip：

- `GET /repos/QQueng/Horizon/actions/runs/{run_id}/artifacts`
- `GET /repos/QQueng/Horizon/actions/artifacts/{artifact_id}/zip`

zip 里的路径是 `digest/horizon-zh.md`。这不是 GitHub Pages，页面发布保持关闭。

## 仍然关闭

邮件、微信、Webhook 和 GitHub Pages 保持关闭。工作流不接收 Webhook 地址，也不推送 `gh-pages`。

调用模型前仍需要的 secret 名称：`DEEPSEEK_API_KEY`。
