# Burp 真实运行验证

格式版本 1。

## 目的与范围

为 [issue #19](https://github.com/2233admin/reverse-skill-evolver/issues/19) 验证真实 Burp 中的扩展请求、代理历史、技术头、RE2J、攻击统计、padding 和截止行为。所有目标为自有 loopback fixture。运行中发现缺失 HTTP 响应被算作命中，随后修正发送边界并重新运行。

## 状态与批准记录

运行记录日期：2026-10-12。实际运行证据已取得；报告编写时尚未合入 main，issue #19 保持开放。后续整合状态以 PR #23、#24 和 issue #19 的远端记录为准。

分支：`fix/burp-missing-response`。原始运行基于 PR #23 的 `3e81a0689093eef5c0c0001f82fb1e4ef26ca526`；集成时更新到 `16accf5fea1560cf2abcb44d814aa7c184e04fbc`。

记录粒度：逐提交记录。实际修复运行与 JAR 对应 `d19105f6f7843f7dd28becdcfcdcdc0167d2b86c`。集成更新额外继承 PR #23 对数组 padding 的拒绝检查及 `[3]` 回归；这项变化由确定性回归和 CI 验证，未重跑真实 Burp，不能将下方 JAR 哈希当作集成版本的哈希。

授权来源：本会话用户的既有审核修正授权，以及“那我们拿工具实际测试1”。用户随后报告“Burp 安装了”；真实窗口确认已进入 Community 临时项目。用户最新指令“测试通过那就合并分支”授权验证后整合 PR #23 和 #24。没有可发布的聊天链接；实际合并状态与提交以两个 PR 的远端记录为准。

## 环境与对象

| 对象 | 实际值 |
|---|---|
| Burp | Community Edition 2026.9.2，build 54622 |
| JVM / 扩展 class format | Temurin 25.0.4.1 / Java 21 |
| 扩展版本 | Burp MCP 2.0.0 |
| 原 JAR SHA-256 | `6646c68906d21c12b219d9b5b12ec6ff2aa90ead82fb31fa8a1c16f0602aa2e3` |
| 修复 JAR SHA-256 | `6c3e02759cc5b43dee78d2ded5ec350d0f23cf2aa9b8f2ca1d5ee38acd868492` |
| 官方 Burp JAR SHA-256 | `3571f8cadbfd65b0b090d2753735c40b76ad7fdde0b927df2b22ec46ea09693a`，与[官网下载页](https://portswigger.net/burp/downloads)一致 |
| 真实加载方式 | `--developer-extension-class-name=com.burpmcp.BurpMcpExtension`，从构建后的 JAR classpath 加载；无界面模式 |
| API / proxy / fixture | `127.0.0.1:9876` / `127.0.0.1:8080` / `127.0.0.1:18089` |

用户亲自完成首次协议页。GUI 操作没有完成手工 JAR 安装验证，随后使用 Burp `--help` 中列出的开发加载入口。该真实进程产生了界面相关的 `no ComponentUI class` 和 `NullPointerException` 启动异常，但已启动代理、Montoya 扩展和 MCP endpoint。本结论限于下面实际通过的网络与 API 场景。

## 证据表

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| 原实现存在缺响应误报 | 同一自有 fixture；[baseline.json](baseline.json) | 63 项记录中 53 项通过，10 条断连路径失败。七类攻击收到 status 0、空 body 后报告命中；三类直接发送返回 status 0 而非错误。退出码 1。 |
| 修复后的实际检查通过 | [verified.json](verified.json)，完整模式 | 67 项记录全部通过，退出码 0。包含 61 个工具案例、4 次代理播种、2 项独立网络观察，涉及 17 种工具；不是 67 种工具。 |
| 真实 MCP stdio 入口可用 | [mcp-verified.json](mcp-verified.json) | initialize、tools/list、encode、burp_version 的四次请求通过；发现 63 个工具。三个数字工具 schema 的 padding maximum 为 1024。未逐个调用全部 63 个工具。 |
| Proxy 分页与过滤成立 | `history-page`、`history-filter`、`history-end` | 四条已知真实代理请求，最新优先、过滤后索引及 total 保留符合预期。 |
| 技术头匹配正确 | `sitemap-fixture-rows`、`technology-headers` | SiteMap 保留四条真实响应，另有推断的 GET `/hist/post`、status 0。采样数与实际 SiteMap 一致；三个支持头匹配，两个近似名称排除。 |
| RE2J 完整匹配与错误成立 | search、extract、grep、unsupported 案例 | 完整 `Token:abc` 匹配、大小写规则和不支持 lookaround 的操作错误符合预期；拒绝模式没有 fixture 流量。 |
| 缺响应得到正确处理 | 七类攻击、三个直接发送的 disconnect 案例 | 攻击 errors 1、hits 0；Cluster Bomb 保留尝试计数 1，其他攻击 completed count 0。三个直接发送返回操作 error。有效 204 空响应和 500 响应保留原成功条件与字段。 |
| padding 保护覆盖实际入口 | 三个数字工具的 padding 案例 | 1024 接受，1025 在发送前拒绝；整数回绕值拒绝。巨大值使用空范围，并仅在 1025 拒绝已观察后测试。 |
| 截止返回可观察 | `deadline-slow-seq`、`deadline-slow-async` | 顺序 120.0040 秒、并发 120.0037 秒返回，均 `timed_out:true`、无 hit；顺序 errors 1、并发 errors 0。 |
| 本次在途连接终止可观察 | 两项 `observation-*` 和原始 fixture events | 130 秒内仅顺序候选 0、并发候选 0/1 到达，无截止后新流量。以本轮运行起点计，三条慢连接约 120.545 秒检测到 EOF；探测周期为 0.25 秒。125 秒后的写入以 WinError 10053 失败。不能据此给出所有版本、目标和请求都能取消的保证。 |
| 确定性缺陷回归成立 | Gradle `schedulerRegressionTest` 红，再 `check jar` 绿 | 原实现在 `intruderAttack: 0` 失败；修复后 `BUILD SUCCESSFUL`，退出码 0。方法级矩阵覆盖十条发送路径的 null 结果、null 响应、status 0、204、500。 |

原始记录由主执行者实际运行产生；独立只读复审核对了 case / fixture JSONL 与 summary 完全一致、源版本、十条缺响应路径、截止和 EOF/写入事件。独立复审未代替运行，也未自行重跑。

fixture 的请求线程随后改为非守护线程，让 `server_close()` 在关闭事件日志前等待它们结束。使用本目录发布的脚本重跑完整模式，[joined-verified.json](joined-verified.json) 的 67 项再次全部通过，退出码 0，最后一个事件的 active count 为 0。这次修改仅涉及 fixture 清理，生产代码仍为 `d19105f`。

## 重现入口

需要用户已同意使用协议的 Burp Community 2026.9.2 官方 JAR、Java 21 或更高、Node 和 Python。使用独立的测试数据目录，确保这三个 loopback 端口可用。不要复用含私人代理流量的 Burp session。

从仓库根目录构建：

```powershell
cd burp-mcp-full
.\gradlew.bat --offline --no-daemon check jar
cd ..
```

将官方 JAR 放在仓库根目录。创建独立测试目录及空项目配置，然后在一个终端启动真实 Burp：

```powershell
New-Item -ItemType Directory -Path burp-live-state/home,burp-live-state/temp,burp-live-state/data -Force
Set-Content -LiteralPath burp-live-state/project.json -Value '{}' -Encoding utf8NoBOM
java -Djava.awt.headless=true -Xmx1g `
  -Duser.home=./burp-live-state/home -Djava.io.tmpdir=./burp-live-state/temp `
  --add-opens=java.base/java.lang=ALL-UNNAMED `
  --add-opens=java.desktop/javax.swing=ALL-UNNAMED `
  --add-opens=java.desktop/java.awt=ALL-UNNAMED `
  --add-opens=java.desktop/java.awt.color=ALL-UNNAMED `
  --add-opens=java.base/javax.crypto=ALL-UNNAMED `
  --add-opens=jdk.crypto.cryptoki/sun.security.pkcs11=ALL-UNNAMED `
  -cp 'burpsuite_desktop_v2026.9.2.jar;burp-mcp-full/build/libs/burp-mcp-full.jar' `
  burp.StartBurp --data-dir=./burp-live-state/data `
  --config-file=./burp-live-state/project.json `
  --developer-extension-class-name=com.burpmcp.BurpMcpExtension --disable-auto-update
```

在第二个终端执行：

```powershell
python reports/burp-live-2026-10-12/mcp_smoke.py
python reports/burp-live-2026-10-12/burp_live.py --quick
python reports/burp-live-2026-10-12/burp_live.py
```

fixture 为每轮生成唯一前缀，使用显式 HTTP proxy 请求捕获流量。正常回复带可核对的技术头和 token；500 回复 `FAIL`；disconnect 直接关闭 socket；慢回复等待 125 秒。运行脚本创建新目录，记录输入、输出、时间、socket EOF 和写入结果，并在任意断言失败时以 1 退出。

`burp_live.py` 的 source label 指向本次被验证的生产提交；重现其他源码时应修改该标签并另外记录实际 JAR 哈希，不能仅凭标签断言加载版本。

## Issue #19 验收对应与缺口

| 验收条件 | 证据 | 状态 |
|---|---|---|
| 构建 JAR、真实加载并实际工具请求 | 构建、JAR 哈希、真实 Montoya、MCP 四次请求和 61 个工具案例 | 通过：开发加载入口；手工 GUI JAR 加载未验。 |
| 分页、过滤和技术头 | history / sitemap / technology 案例 | 通过。 |
| 完整正则及清晰错误 | search / extract / grep / unsupported 案例 | 通过。 |
| 正常、失败、慢请求及统计、正 timeout、截止与提交边界 | 十条发送路径、两个 deadline 案例、确定性 options / scheduler 回归 | 通过已覆盖场景；真实 RequestOptions 的 timeout 数值未被 endpoint 暴露，正数计算由源码及确定性回归支持。网络到达时间不能直接证明精确 Java 提交时刻。 |
| 取消后的实际 transport | 130 秒 fixture EOF 和写入事件 | 通过本次连接观察；通用取消保证不成立。 |
| 可复核报告、fixture 和清理 | 本目录脚本、原始摘要及本报告 | 报告、重现入口和下方清理回执已交付。 |

未验证全部 63 个工具、Pro 功能、GUI 安装路径、其他 Burp/JDK 版本、真实 IDA/OMP。既有 17 项审计发现和旧 build issue #22 没有被本次修复覆盖；Node bridge 的操作错误 `isError` 标记仍属于已知未处理项。

Repowise 的 14 条提示已在当前差异上独立复核。两条 critical 来自测试矩阵和场景登记方法的复杂度阈值，其余为嵌套、长度和异常捕获等指标，没有确认生产缺陷。case、seed 和 runner 捕获异常后记录失败并退出 1；fixture 的晚写异常作为独立观察保留。自动断连断言以操作输出为准，本次十条断连案例均另外核对了新到达、主动关闭和 finished 事件；未来扩展失败路由时应保留这一来源核对。覆盖率没有上传，bot 的旧索引推断不代替实际执行证据。

## 进度与清理

构建、独立审查、实际红绿对照、截止观察和证据整理完成。报告编写时远端整合待执行；后续整合见 PR 记录，生命周期由 issue-workflow 按证据及相关 PR 状态判定。

测试脚本在退出时停止并 join 自有 fixture，没有调用清空他人 Proxy history 的操作。2026-10-12 09:47:16 UTC，主执行者核对测试进程命令行身份后终止自有 Burp PID 21552，复核 9876、8080、18089 均没有监听者。JAR 和原始记录保留供复查，没有发布 release。

## 现状文档与更正记录

现状文档：`burp-mcp-full/README.md` 已说明缺响应错误、有效 204/500 行为。没有改变先前授权或长期产品选择。

意外发现：真实 Montoya 缺响应对象不同于先前 null mock；SiteMap 与 Proxy history 不具有一一对应数量。两项均在本次记录和相应回归中表达。

本目录文件：`README.md` 为综合报告；`baseline.json` / `verified.json` 为原实现与修复后完整实际记录；`joined-verified.json` 为等待 fixture 线程退出后的再次完整重放；`mcp-verified.json` 为真实 stdio 请求响应；两个 Python 文件为重现工具。

结项后的更正与补记：无，issue 尚未结项。
