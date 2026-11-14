# Fork 部署

仓库：`QQueng/Horizon`。默认分支：`main`。

工作流文件：`.github/workflows/daily-summary.yml`。Actions 名称：`Horizon daily digest`。

## 时间

定时表达式是 UTC `0 0 * * *`，对应每天北京时间 08:00，含周末。GitHub Actions 可能晚于这个时间才开始。这不是准点生成或送达的保证。

定时触发在预检通过后运行流水线。手动 `workflow_dispatch` 在 `run_pipeline` 为 false 时只做预检。

## 现在的日报

只采集和处理论财经与市场。AI与科技、工程与建筑、历史与人文的信息源已从运行配置中去掉，避免继续为它们调用模型。

总量最多 10 条，财经与市场这一组最多 10 条。分数低于 7 的条目不会为了凑满 10 条留下。抓取窗口是最近 24 小时。输出语言是中文。条目标题和来源行保留原文链接。

中文时间按北京时间显示，并标明「北京时间」。试运行 `43589835434` 里，带 `+0800` 的发布时间曾按 UTC 钟面写出，所以比中文原文早 8 小时。模型提示现在同时给出 UTC 和北京时间。

财经 Profile 要求保留来源对人事变动的说法：来源写辞职时，不要改成被解职。它也要求不要把明显早于发布 24 小时的事件写成当天新闻。这些是约束，不能保证模型不再改写。

## 财经来源

2026-11-14 核对过，均为带日期的公开 RSS，且不是同一家：

| 名称 | 链接 |
| --- | --- |
| 华尔街见闻 | https://dedicated.wallstreetcn.com/rss.xml |
| 日经中文 | https://cn.nikkei.com/rss.html |
| FT中文网 | https://www.ftchinese.com/rss/news |
| 经济观察网 | https://www.eeo.com.cn/rss.xml |
| Investing.com 股市 | https://www.investing.com/rss/news_25.rss |

## 模型

`deepseek-flash`，接口 `https://api.deepseek.com`。思考模式按官方文档默认开启，这里设为 `disabled`。密钥名称仍是 `DEEPSEEK_API_KEY`。定时运行和手动打开 `run_pipeline` 会调用付费接口。只做预检不会调用。

依据仍是 https://api-docs.deepseek.com/ 、https://api-docs.deepseek.com/quick_start/pricing/ 和 https://api-docs.deepseek.com/guides/thinking_mode 。

## 产物

成功生成非空中文 Markdown 后，上传 artifact `horizon-digest`，路径 `digest/horizon-zh.md`，保留 7 天。这是给助手读取的载体，不是发给用户的附件。失败不上传占位日报。

- `GET /repos/QQueng/Horizon/actions/runs/{run_id}/artifacts`
- `GET /repos/QQueng/Horizon/actions/artifacts/{artifact_id}/zip`

邮件、微信、Webhook 和 Pages 发布保持关闭。
