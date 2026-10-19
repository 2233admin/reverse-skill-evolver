---
name: chains
description: Decision-skeleton reference for reverse-engineering and security routes. Each file distils the bundled field-journal seeds into scene/criterion/turn lines so an agent can locate its current situation without reading every case record. Use when a routed task needs decision support mid-execution (卡住怎么办/该换维度吗/这个现象说明什么), alongside the selected module's own SKILL.md.
---

# Chains — 决策骨架

本目录把 `field-journal/` 的**史料**（"某次怎么做成"）蒸馏为**判据**（"遇到 X 就先问自己 Y"）。
史料是 case record，骨架是决策反射；两者互补，不互相替代。

## 与 field-journal 的分工

| | `field-journal/` | `chains/`（本目录） |
|---|---|---|
| 形态 | 单次项目复盘：场景分类 → 执行链路 → 踩坑 → 工具链发现 | 跨项目判据：`场景\|判据\|转向` |
| 读法 | 新任务开始前查索引找同类经验 | 执行中定位当前场景，决定下一步 |
| 更新 | 每次任务后回写（见 `../ROUTER.md` 自动进化段） | 从 field-journal 再蒸馏；不直接写 |

## 文件

| 文件 | 覆盖 |
|---|---|
| `rev.md` | 二进制逆向：入口分诊、符号/字符串恢复、算法与密钥定位、动态与注入链、JS 签名、固件与硬件（IoT） |
| `app.md` | 移动端：Frida 环境与反检测、证书校验绕过、代码定位、Unity IL2CPP 游戏 |
| `web.md` | Web：探测与 OOB、认证与越权、SSRF 与云侧、XML 实体注入、证据与交付 |
| `pwn.md` | 二进制利用：保护分诊、信息泄漏两阶段、运行时陷阱 |
| `priv.md` | 提权：容器逃逸路径选择、逃逸后横向、验证边界 |
| `ad.md` | 内网/AD：证书服务、Kerberos 攻击、中继与强制认证、内网推进 |
| `recon.md` | 侦察：协议逆向（PCAP）、目标排序、推进纪律 |

## 行格式

```text
- 场景:<此刻的处境>|判据:<如何判断>|转向:<因此做什么>〔来源条目〕
```

末尾的 `〔…〕` 是溯源标记，指向 `field-journal/` 中的原始条目；改动骨架前应先读该条目。

## 使用

1. 由 `routing` 选定模块后，按任务领域读取对应骨架文件。
2. 逐条匹配"场景"；命中则按"判据"验证、按"转向"行动。
3. 未命中任何场景 → 按所选模块的 `SKILL.md` 正常推进，不必强套骨架。
4. 骨架与现场证据冲突时，**以现场证据为准**；冲突应回写为新的 field-journal 条目。

## 边界

- **本目录不复制外部仓库文本。** 结构与 `agent/chainskel/`（ARTEX, AGPL-3.0）同类，但内容全部蒸馏自本包 `field-journal/` 自有条目，逐行标源。
- 骨架是**启发式提示**，不是授权、不是 oracle、不替代所选模块的工作流或 GoAL 契约。
- 本目录**尚未接入 `routing.json`**：当前需按上述"使用"手动定位。路由注入是独立变更，未获批前不得假设已生效。
