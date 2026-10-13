# 项目经验索引

> 本文件由 AI 在每次完成逆向/渗透/安全项目后自动维护。
> 新任务开始前先查阅本索引，复用已有经验，避免重复踩坑。
> 带 [种子] 标记的条目是预置的教科书级参考，非真实项目。

> 恢复来源：Git `070bf87` 的可读索引；2026-05-26 新增条目以现存同日日志补齐，后续脱敏占位保留。本次恢复不改变经验验证层级。
> 后续新增先例段落已损坏，未找到可靠原文，加载顺序与授权措辞标为未恢复；保留原有引用：[precedent-auth.md](precedent-auth.md)、[precedent-reverse.md](precedent-reverse.md)、[precedent-pentest.md](precedent-pentest.md)。具体操作授权仍须依据当前任务。

## 检索三轴

新任务开始前按这三个维度依次查找，命中任一即可读对应日志：

1. **按场景类型**（最常用）— 当前任务属于"APK 逆向 / Web 渗透 / 二进制分析 ..."哪一类，直接看下方分类
2. **按成功技术** — 已经知道要用什么招（如 Frida bypass、SSRF→元数据、ESC1 提权），看下方"高频成功模式"
3. **按目标实体** — 已经识别目标特征（Spring Boot 后台 / OkHttp Pin / Vue SPA / OkHttp 证书校验），看下方"实体倒排"

写新经验时，文件名采用 `YYYY-MM-DD_<场景>-<目标技术>-<结果>.md`，便于 `grep` 直接命中（例：`2026-05-15_apk-okhttp-bypass-success.md`）。

## 按场景分类

### APK 逆向
- [2026-05-15] Cellular-Pro MuMu 闪退修复 — 关键词: APK, MuMu, KSAd, Kuaishou, fragment生命周期, SuperNotCalledException
- [种子] APK Frida 绕过 OkHttp SSL Pinning — 关键词: Frida, OkHttp, SSL Pin, CertificatePinner, objection, frida-multiple-unpinning, 反 Frida 检测
<!-- 格式: - [YYYY-MM-DD] 项目简称 — 关键词: keyword1, keyword2, keyword3 -->

### iOS 逆向
- [种子] iOS 越狱检测绕过 + 抓包 — 关键词: iOS, 越狱检测, jailbreak detect, objection, frida-ios-dump, mitmproxy, NSURLSession

### JS 签名 / Web 逆向
- [种子] JS 签名逆向（Webpack+AES+时间戳）— 关键词: webpack, HmacSHA256, sign参数, 断点, initiator

### 二进制分析
- [种子] ELF 自解压加载器逆向 — 关键词: ARM64, LZSS, mmap, 自解压, 反分析, 损坏PHDR
- [种子] Go 恶意软件逆向（stripped+Garble）— 关键词: Go, Garble, GoReSym, GoResolver, C2, AES密钥
- [2026-05-15] lumine v0.9.1 Go TLS 分片代理逆向 — 关键词: Go, TLS, 分片代理, GoReSym, 源码重建, PE32+, capstone

### 游戏逆向
- [种子] Unity IL2CPP 还原 + Frida hook — 关键词: Unity, IL2CPP, Il2CppDumper, frida-il2cpp-bridge, global-metadata, Android 游戏

### CTF / Pwn
- [种子] CTF Pwn x64 栈溢出 + ROP → system — 关键词: pwn, x64, ROP, ret2libc, pwntools, pwndbg, ROPgadget, libc-database, 栈对齐

### 抓包分析
- [种子] PCAP 自定义二进制协议逆向 — 关键词: PCAP, Wireshark, scapy, Kaitai Struct, TLV, 长度前缀, 熵分析, dissector

### 固件 / IoT
- [种子] IoT 路由器固件提取 + UART 拿 root — 关键词: binwalk, unblob, squashfs, UART, USB-TTL, U-Boot, init=/bin/sh, firmwalker, FirmAE

### 渗透测试
- [种子] Web API 未授权访问+IDOR — 关键词: REST API, IDOR, 越权, Swagger暴露, FFUF
- [种子] AD CS ESC1 证书模板滥用 → 域管 — 关键词: certipy, AD CS, ESC1, 证书, DCSync, Kerberos
- [种子] SSRF → 云元数据 → AK/SK → OSS 数据 — 关键词: SSRF, 云元数据, 169.254.169.254, AK/SK, IMDSv2
- [种子] NTLM Relay + Coercer → 域管（无密码） — 关键词: NTLM Relay, Coercer, ntlmrelayx, 约束委派, S4U, PetitPotam
- [种子] Log4Shell JNDI 注入 RCE — 关键词: Log4Shell, CVE-2021-44228, JNDI, LDAP, 本地 gadget, WAF 绕过, interactsh
- [种子] Kerberoasting → 离线破 → DA — 关键词: Kerberoasting, GetUserSPNs, hashcat 13100, BloodHound, AS-REP Roasting, OneRule
- [种子] XXE 盲注 OOB 外带 — 关键词: XXE, OOB, 外部 DTD, 参数实体, php://filter, docx 上传, 内网 SSRF
- [2026-05-16] {target_domain} Mass Assignment 提权 — 关键词: Spring Boot, MyBatis-Plus, SaToken, Mass Assignment, Swagger泄露, 权限提升, Vue SPA, temp mail, JS静态分析, 前端路由绕过, DTO缺失, 限速绕过
- [2026-05-17] Vue SPA + Spring Boot 后台 Web 渗透（API Key 硬编码 / admin_path 泄露 / Actuator）— 关键词: API Key硬编码, Vue SPA静态分析, admin_path泄露, 验证码禁用, Actuator, Cloudflare WAF, Vite bundle
- [2026-05-25] CF Access 兄弟子域配置错误 + Cookie 投毒 → Session Fixation — 关键词: Cloudflare Access, Zero Trust, CF Worker, 兄弟子域, wildcard证书, Set-Cookie透传, 父域cookie, Session Fixation, data URI XSS, 响应头注入, Open Proxy, Email OTP, CT日志, certspotter

- [2026-05-26] CTF Web 网关限速绕过与信息暴露 — 关键词: New API, rate limit bypass, X-Forwarded-For, /api/status, /api/pricing, 信息泄露

### 云 / 容器 / K8s
- [种子] 容器逃逸 → K8s 集群接管 — 关键词: 特权容器, cap_sys_admin, docker.sock, K8s SA token, hostPath, deepce, kdigger, peirates, CVE-2022-0492, DirtyPipe

### CTF
<!-- 格式: - [YYYY-MM-DD] 项目简称 — 关键词: keyword1, keyword2, keyword3 -->

### 抓包分析（实战项目）
<!-- 格式: - [YYYY-MM-DD] 项目简称 — 关键词: keyword1, keyword2, keyword3 -->

### 其他
<!-- 格式: - [YYYY-MM-DD] 项目简称 — 关键词: keyword1, keyword2, keyword3 -->

---

## 高频踩坑 Top 5

1. 文件后缀不可信 — 永远用 `file` 命令确认真实类型
2. Go 二进制函数太多看不过来 — 用 GoReSym 恢复后按包名过滤
3. FFUF/扫描被 WAF 拦截 — 降低速率 + 换 User-Agent
4. 解压器/解密器 Python 实现输出错误 — 仔细对照汇编的进位/溢出行为
5. SRC 报告被拒 — 必须有可复现的 curl 命令，不能只有截图

---

## 高频踩坑新增

6. Swagger Knife4j 页面是交互式攻击面板 — 不要只看 JSON，`/doc.html` 页面提供"在线调试"功能，可直接在页面试用任意 API
7. Spring Boot Mass Assignment 通常隐藏在建表脚本可以看到所有字段，而 Controller 直接收 Entity 的地方
8. IP 被限速后不要硬等 — 转做 JS 静态分析，前端 bundle 包含完整 API 端点清单和请求参数格式
9. Frida 注入要用 spawn 模式（`-f` + `--no-pause`），attach 模式经常错过初始化期 hook
10. ROP 调 `system` 在新版 glibc 必须栈对齐到 16 字节，前面加一个 `ret` gadget
11. UART 看到字符乱码先互换 TX/RX，还乱码再换波特率
12. Log4Shell 高 JDK 版本（8u191+）必须用本地 gadget chain，不要尝试远程类加载
13. 容器逃逸先看 `/proc/self/status` 的 `CapEff`，不要凭直觉乱试
14. Kerberoasting 离线破解之前先用 `nxc` 验证凭据，避免 hashcat 跑几个小时拿到的密码其实早过期
15. XXE 全无回显时优先 OOB 两层 DTD，DNS 通 HTTP 不通就走 DNS exfil

16. 登录限速测试使用“同参数 + 变源头”对照；429 baseline → header mutation → status diff。结论与覆盖以同日日志为准。

## 累计统计

- 总项目数: 22（含 17 个种子 + 5 个真实项目）
- 新增模式数: 28
- 工具链修复数: 0
- 最近更新: 2026-05-26

---

## 高频成功模式（按技术）

> 已经知道想用什么招，从这里反查有没有现成案例。新增日志时同步在此追加 1 行。

### Frida / 动态插桩
- OkHttp 证书校验绕过 — `seed-008_apk-okhttp-ssl-pin-bypass.md`
- 越狱检测绕过 — `seed-009_ios-jailbreak-detect-bypass.md`
- IL2CPP method hook — `seed-014_unity-il2cpp-reverse.md`
- root 检测绕过 — _尚无_

### Web 渗透
- Mass Assignment 提权 — `2026-05-16_pentest-personalblog-fun-mass-assignment.md`
- Swagger / Knife4j 暴露 → API 调试 — `2026-05-16_pentest-personalblog-fun-mass-assignment.md`、`2026-05-17_pentest-vue-spa-actuator-leak.md`
- API Key 硬编码 / Vue SPA 静态分析 — `2026-05-17_pentest-vue-spa-actuator-leak.md`
- IDOR / 越权 — `seed-003_web-api-auth-bypass.md`
- SSRF → 云元数据 → AK/SK — `seed-006_ssrf-cloud-metadata.md`
- Log4Shell / JNDI 注入 — `seed-012_log4shell-jndi-rce.md`
- XXE OOB 外带 — `seed-017_xxe-oob-exfil.md`
- **CF Access 兄弟子域绕过(wildcard 证书 + Application 单子域)** — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`
- **跨子域 Cookie 投毒 / Session Fixation(代理透传 Set-Cookie)** — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`
- **HTTP 代理类目标 7 道检测**(Set-Cookie 透传 / 响应头透传 / data: scheme / POST 透传 / scheme 白名单 / redirect 跟随 / 缓存键) — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`
- **data: URI 反射型 XSS(合法域钓鱼)** — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`

- **登录限速绕过（X-Forwarded-For）** — `2026-05-26_pentest-newapi-rate-limit-bypass.md`
- **匿名接口信息暴露（/api/status + /api/pricing）** — `2026-05-26_pentest-newapi-rate-limit-bypass.md`

### Active Directory
- AD CS ESC1 → DCSync — `seed-005_ad-certipy-esc1.md`
- NTLM Relay + Coercer → 域管 — `seed-007_ntlm-relay-coercer.md`
- Kerberoasting → 离线破 → DA — `seed-013_kerberoasting-spn.md`

### 容器 / 云原生
- 容器逃逸（特权 / cap / docker.sock / SA token） — `seed-016_k8s-container-escape.md`
- 云元数据 SSRF → AK/SK — `seed-006_ssrf-cloud-metadata.md`

### 二进制 / 逆向
- Go stripped + Garble + GoReSym 还原 — `seed-002_go-malware-stripped.md`、`2026-05-15_lumine-go-reverse.md`
- ELF 自解压 + LZSS — `seed-001_elf-packed-loader.md`
- JS 签名（Webpack + AES）— `seed-004_js-sign-webpack.md`
- Android Fragment 生命周期修复 — `2026-05-15-cellular-pro-mumu-ksad-fragment-fix.md`

### CTF / Pwn
- ret2libc + ROP 标准两阶段 — `seed-010_ctf-pwn-rop-x64.md`

### 协议 / 抓包
- 自定义二进制协议（TLV / 长度前缀）逆向 — `seed-011_pcap-protocol-reverse.md`

### 固件 / 硬件
- binwalk/unblob 提取 + UART 拿 root — `seed-015_iot-firmware-uart.md`
- U-Boot init=/bin/sh 单用户 bypass — `seed-015_iot-firmware-uart.md`

---

## 实体倒排（按目标特征）

> 已经识别目标长什么样，从这里反查同类目标的处理路径。

### Java 后端
- Spring Boot + MyBatis-Plus + SaToken — `2026-05-16_pentest-personalblog-fun-mass-assignment.md`
- Spring Boot Actuator 暴露 — `2026-05-17_pentest-vue-spa-actuator-leak.md`
- Log4j2 受影响版本 — `seed-012_log4shell-jndi-rce.md`
- 接受 XML/SOAP/docx 上传的 Java 应用 — `seed-017_xxe-oob-exfil.md`

### 前端框架
- Vue SPA 静态分析 — `2026-05-16_*`、`2026-05-17_*`
- Webpack bundle 还原 — `seed-004_js-sign-webpack.md`

### Android
- KSAd / Kuaishou 广告 SDK — `2026-05-15-cellular-pro-mumu-ksad-fragment-fix.md`
- MuMu 模拟器适配 — `2026-05-15-cellular-pro-mumu-ksad-fragment-fix.md`
- OkHttp + 自定义 CertificatePinner — `seed-008_apk-okhttp-ssl-pin-bypass.md`
- Unity IL2CPP 游戏 — `seed-014_unity-il2cpp-reverse.md`

### iOS
- 越狱检测 + SSL Pin 双重防护 — `seed-009_ios-jailbreak-detect-bypass.md`

### 二进制语言
- Go (Garble obfuscated) — `seed-002_*`、`2026-05-15_lumine-go-reverse.md`
- ARM64 ELF — `seed-001_elf-packed-loader.md`
- x86_64 漏洞 ELF (NX + 无 PIE) — `seed-010_ctf-pwn-rop-x64.md`

### 协议 / 网络
- New API 网关限速与匿名接口 — `2026-05-26_pentest-newapi-rate-limit-bypass.md`
- 自定义 TCP 二进制协议 — `seed-011_pcap-protocol-reverse.md`
- AD Kerberos / SPN — `seed-005_*`、`seed-007_*`、`seed-013_kerberoasting-spn.md`

### 云 / 基础设施
- 云元数据接口 (169.254.169.254) — `seed-006_ssrf-cloud-metadata.md`
- AD CS — `seed-005_ad-certipy-esc1.md`
- WAF (Cloudflare) — `2026-05-17_pentest-vue-spa-actuator-leak.md`
- **Cloudflare Access / Zero Trust(Email OTP, wildcard 子域配置错误)** — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`
- **Cloudflare Worker(`fetch` 自动拦私有 IP,Set-Cookie 透传)** — `2026-05-25_pentest-cf-access-sibling-subdomain-cookie-poisoning.md`
- Docker / containerd / K8s — `seed-016_k8s-container-escape.md`

### 硬件 / 固件
- ARMv7 / MIPS 路由器固件 + UART — `seed-015_iot-firmware-uart.md`
