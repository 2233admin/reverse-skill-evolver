# v1.2.0-beta.1 测试版

基于 main 的 `39d1d19`，包含本轮已合并修复和 Agent 蜂群。Python 版本为 `1.2.0b1`；发布是 Pre-release。完整 ZIP 包含源码、`skills/`、`.omp/skills/`、文档和 `packages/` 下的安装包。wheel 仅安装 Python CLI，不注册 OMP skill 或修改模型配置。

## 安装与检查

解压完整 ZIP，进入其中的 `reverse-skill-evolver-v1.2.0-beta.1` 目录。使用 Python 3.10+ 和一个单独环境；Windows PowerShell 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\packages\reverse_skill_evolver_cli-1.2.0b1-py3-none-any.whl
.\.venv\Scripts\reverse-skill.exe --version
.\.venv\Scripts\reverse-skill.exe --help
.\.venv\Scripts\reverse-skill-swarm.exe --help
```

预期版本 `1.2.0b1`，两条命令能显示帮助。Linux/macOS 使用 `.venv/bin/python`、`.venv/bin/reverse-skill` 和 `.venv/bin/reverse-skill-swarm`。只检查帮助不调用模型或启动 IDA。

## 先测试蜂群

准备自己允许发送给当前 OMP 模型的 UTF-8 证据文件 `evidence.txt`。确认 OMP CLI 可用，并复用已配置模型；下面显式限制三次逻辑调用，即协调、一个分析任务、汇总各一次。输出目录必须是新目录。

```powershell
.\.venv\Scripts\reverse-skill-swarm.exe --goal "列出证据支持的结论及未知项" --context .\evidence.txt --output .\runs\beta-swarm-001 --max-calls 3 --max-tasks 1 --max-parallel 1 --timeout 60 --json
```

检查 `run.json` 的逻辑调用计数、任务状态及汇总，以及 `context.txt` 的字节和 SHA-256 是否与输入一致。`analysis_status` 始终是 `advisory`；成功执行不等于结论已验证。三次是逻辑调用预算，provider 内部重试、Token 和费用另计。

再次用新的输出目录测试四次调用/两个任务/并发二；Ctrl+C 后检查已运行结果保留，未开始任务为 cancelled。已有输出目录应被拒绝覆盖。OMP 必须返回规定 JSON；真实模型不遵守格式也是本次测试需要记录的结果。

## IDA 与 Burp

IDA 前提是本机已安装、已许可的 IDA/idalib 和可用的 `idalib-mcp`。先按 [首页代表任务](README_zh.md#0-先完成一条本地-ida-任务) 检查服务、打开自己的样本并保存 JSON。服务失败时检查 PID/日志；手动替换只针对确认的目标端口。

Burp 扩展使用 Java 21+，在 Burp 的 Extensions → Add → Java 中选择 `packages/burp-mcp-full.jar`；Node bridge 的接入、重试及错误测试见 [Burp 说明](burp-mcp-full/README.md)。JAR 的既有组件版本是 2.0.0，此测试包按本次源提交构建，不改变组件版本约定。

OMP 原生 workflow 要从本完整源码目录进入，或复制完整 `.omp/skills/` 对应子目录；pip 不会自动安装这些 skill。真实 eval 的显式模块导入已有限定证据，自动发现需要这次实际核对。

## 反馈

请在仓库新建 issue，附操作系统、Python/OMP/IDA/Burp 版本、测试版号、实际命令、预期/实际结果和脱敏后的 `run.json`/错误日志。不要提交 API key、模型配置秘密或不允许分享的样本。

当前未完成真实蜂群模型协作质量、真实用户首次上手、Burp GUI 和设备/远端同步验收。构建与受控替身测试见 [验证记录](BETA-VALIDATION.md)，测试版不作稳定版或任意目标兼容承诺。
