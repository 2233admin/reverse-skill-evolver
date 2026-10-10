# BurpSuite MCP Full Control Extension

通过 MCP 协议完整控制 BurpSuite 的所有核心功能。跨平台支持 Windows / Linux (Kali) / macOS。

## 快速开始

### 1. 编译扩展

**Windows**:
```cmd
cd burp-mcp-full
build.bat
```

**Linux / Kali / macOS**:
```bash
cd burp-mcp-full
chmod +x build.sh
./build.sh
```

手动构建需要 JDK 21+ 和 `curl`；Windows 使用 `JAVA_HOME`，未设置时使用 PATH 中的 JDK。
两个脚本先确保依赖存在（下载失败直接退出），仅在输出 JAR 比所有 Java 源文件和
依赖 JAR 更新时跳过编译与打包；同时间戳或无法检查时间戳时重新构建。

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
| `intruder_attack` | **自动化枚举攻击** | `url_template`, `from`, `to`, `pad_digits`, `method`, `headers`, `success_indicator`, `success_length_not` |
| `intruder_attack_async` | 有界并发枚举；每次最多 50 个在途请求，协调等待上限 120 秒 | `url_template`, `from`, `to`, `threads`；超限返回部分结果与 `timed_out: true`。底层请求的响应读取有超时，建连阶段仍由 Burp 控制 |
| `sitemap` | 查看站点地图 | `url_prefix`, `limit` |
| `intercept_toggle` | 开关拦截 | `enable` |
| `encode` | 编码（Base64/URL） | `input`, `type` |
| `decode` | 解码（Base64/URL） | `input`, `type` |
| `scan` | 启动漏洞扫描 | `url` |
| `add_to_scope` | 添加到 Scope | `url` |

### 正则表达式兼容性

`search_history` 的 `regex`（不区分大小写）和 `extract_from_response` 的 `regex`
使用 **RE2/J 1.8**，避免用户提供的正则触发灾难性回溯。支持常见字符类、
分组、交替和重复；不支持 Java 回溯引擎特有的反向引用（例如 `(a)\1`）、
前后向断言（例如 `(?=...)` / `(?<=...)`）、原子组和占有量词。
非法或不支持的表达式返回现有工具结果中的 `error`，不会回退到 Java 正则引擎。
不区分大小写匹配遵循 RE2/J 的语义；非 ASCII 字符的大小写匹配可能与
原先 `java.util.regex` 的 `CASE_INSENSITIVE` 行为不同。

Java 回归检查：在本目录运行 `gradle performanceRegressionTest`（或 `gradle check`），
覆盖历史分页/顺序、RE2/J 拒绝行为及有界预览；需要 JDK 21+、Gradle 和 Maven 依赖。

## 安装

### 方法 1：直接用预编译 jar

```
1. 下载 burp-mcp-full.jar
2. Burp → Extensions → Add → Extension Type: Java → Select file
3. 加载后在 Output 看到 "[MCP] Server started on http://127.0.0.1:9876"
```

### 方法 2：从源码构建

```bash
cd burp-mcp-full
gradlew.bat jar
# 输出: build/libs/burp-mcp-full.jar
```

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
