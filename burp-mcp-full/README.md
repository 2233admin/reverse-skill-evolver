# BurpSuite MCP Full Control Extension

通过 MCP 协议完整控制 BurpSuite 的所有核心功能。跨平台支持 Windows / Linux (Kali) / macOS。

## 快速开始

### 1. 编译扩展

需要安装 **JDK 21**，并设置 `JAVA_HOME`（或将 `java` 加入 `PATH`）。仓库包含固定版本 **Gradle 8.7** 的标准 Wrapper，无需预装 Gradle；首次构建需要联网下载 Gradle 发行包及 Maven 依赖。发行包通过 Wrapper 中固定的 SHA-256 校验。

**Windows**:
```cmd
cd burp-mcp-full
build.bat
```

**Linux / Kali / macOS**:
```bash
cd burp-mcp-full
./gradlew jar
```

Windows 的 `build.bat` 同样调用 Wrapper 的 `jar` 任务，可从任意工作目录启动，不会覆盖 `JAVA_HOME`。两种方式均生成 `build/libs/burp-mcp-full.jar`；源码、依赖与构建配置未变化时，再次构建会将 `compileJava` 和 `jar` 标为 `UP-TO-DATE`，不重复编译或打包。不要在重复构建前运行 `clean`，否则会删除增量构建输出。

POSIX 快捷入口 `./build.sh` 同样调用固定版本 Wrapper 的 `jar` 任务，可从其他工作目录通过脚本路径启动，并透传 Gradle 参数，例如 `./build.sh --offline --no-daemon`。构建失败时保留 Wrapper 的非零退出码。

运行回归检查（`check` 包含确定性的 `schedulerRegressionTest`）：

```cmd
gradlew.bat check
```

```bash
./gradlew check
```

### 2. 加载到 Burp

```
Burp Suite → Extensions → Add → Java → 选择 build/libs/burp-mcp-full.jar
```

### 3. 配置 MCP 客户端

在任何 MCP 客户端（Claude Code / Kiro / Cursor / Cline / Windsurf）中添加：

```json
{
  "mcpServers": {
    "burpsuite": {
      "command": "node",
      "args": ["<本目录路径>/mcp-bridge.js"]
    }
  }
}
```

### 4. 开始使用

对 AI 说："分析 Burp 代理历史中的请求，找出安全漏洞"

## 功能列表

| Tool | 功能 | 参数 |
|------|------|------|
| `proxy_history` | 查看/过滤代理历史 | `limit`, `offset`, `url_filter`, `method_filter` |
| `send_request` | 通过 Burp 发送 HTTP 请求 | `method`, `url`, `body`, `headers` |
| `send_to_repeater` | 发送请求到 Repeater | `request`, `tab_name` |
| `send_to_intruder` | 发送请求到 Intruder | `request` |
| `intruder_attack` | **自动化顺序枚举攻击**；协调等待上限 120 秒，超限返回 `timed_out: true` | `url_template`, `from`, `to`, `pad_digits`, `method`, `headers`, `success_indicator`, `success_length_not`。响应超时使用剩余时限；建连阶段仍由 Burp 控制，取消不保证终止底层请求。该时限不适用于 `send_request` / Repeater 单次请求 |
| `intruder_attack_async` | 有界并发枚举；每次最多 50 个在途请求，协调等待上限 120 秒 | `url_template`, `from`, `to`, `threads`；超限返回部分结果与 `timed_out: true`。响应超时使用剩余时限；建连阶段仍由 Burp 控制，取消不保证终止底层请求 |
| `sitemap` | 查看站点地图 | `url_prefix`, `limit` |
| `intercept_toggle` | 开关拦截 | `enable` |
| `encode` | 编码（Base64/URL） | `input`, `type` |
| `decode` | 解码（Base64/URL） | `input`, `type` |
| `scan` | 启动漏洞扫描 | `url` |
| `add_to_scope` | 添加到 Scope | `url` |

未收到 HTTP 响应时，攻击工具增加 `errors`，单次发送和 Repeater 工具返回 `error`。有效的 204 空响应和 500 响应保留正常响应统计及原有的成功判定条件。

## 安装

三个数字攻击工具 `intruder_attack`、`intruder_attack_async`、`intruder_with_options` 的 `pad_digits` 上限为 1024。默认值和非正值不补零；超出上限时在构造 payload 或发送请求前返回操作错误。

### 方法 1：直接用预编译 jar

```
1. 下载 burp-mcp-full.jar
2. Burp → Extensions → Add → Extension Type: Java → Select file
3. 加载后在 Output 看到 "[MCP] Server started on http://127.0.0.1:9876"
```

### 方法 2：从源码构建

```cmd
cd burp-mcp-full
gradlew.bat jar
```

```bash
cd burp-mcp-full
./gradlew jar
```

输出：`build/libs/burp-mcp-full.jar`。

## MCP 配置

### Kiro (.kiro/settings/mcp.json)
```json
{
  "mcpServers": {
    "burpsuite": {
      "url": "http://127.0.0.1:9876"
    }
  }
}
```

## 调用示例

### 查看代理历史
```json
POST http://127.0.0.1:9876
{"tool": "proxy_history", "params": {"limit": 10, "url_filter": "personalblog"}}
```

### 发送请求
```json
POST http://127.0.0.1:9876
{"tool": "send_request", "params": {"method": "GET", "url": "https://example.com/api/test"}}
```

### 自动化枚举攻击（核心功能）
```json
POST http://127.0.0.1:9876
{
  "tool": "intruder_attack",
  "params": {
    "url_template": "https://target.com/api/verify?code=§§",
    "method": "POST",
    "from": 0,
    "to": 999999,
    "pad_digits": 6,
    "success_length_not": 176,
    "headers": {"User-Agent": "Mozilla/5.0"}
  }
}
```

### 开关拦截
```json
POST http://127.0.0.1:9876
{"tool": "intercept_toggle", "params": {"enable": false}}
```

## 端口

默认监听 `127.0.0.1:9876`，与 PortSwigger 官方 MCP 扩展相同端口。
如果同时使用官方扩展，需要修改源码中的端口号。
