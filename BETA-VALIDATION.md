# v1.2.0-beta.1 验证记录

2026-10-14；Python 包版本 `1.2.0b1`。源代码基于 main `39d1d194f2597230b3fa53ce586d9de9f07237ef`，本发布分支仅修改版本号、版本断言及发布文档。测试环境为 Windows、Python 3.14.7、Temurin 21.0.12.1+1、Gradle 8.7。

## 证据表

| 结论 | 验证方式 | 结果与局限 |
|---|---|---|
| Python 包可构建 | 亲自执行 `python -m build --no-isolation` | 退出 0；从 sdist 构建 wheel 成功。wheel SHA-256 为 `9f4d45d4089e78e517feb61fe9f896e162d79ed12c84f7ec809066a0f37c8107`。setuptools 提示旧 license 字段格式弃用，当前构建成功。完整 OMP skills 另在完整 ZIP 中提供。 |
| 版本与蜂群源代码回归通过 | 亲自执行 `python -m pytest tests/test_cli.py::test_help_and_version_are_available tests/test_swarm.py -q -p no:cacheprovider --tb=short` | 退出 0；30 passed in 4.88s。原始记录为完整 ZIP 的 `validation/focused-tests.log`。 |
| 安装后的两个 CLI 入口可用 | 在仓库外新建无全局包继承的 venv，安装本 wheel 及依赖；执行 `reverse-skill --version`、两条 CLI 的 `--help`，核对实际模块加载路径 | 各命令退出 0；版本 `1.2.0b1`；模块从该 venv 的 site-packages 加载。原始命令、输出及退出码在完整 ZIP 的 `validation/installed-smoke.json`。 |
| 安装后的蜂群运行路径可用 | 从安装后的 `reverse-skill-swarm.exe` 调用独立 OMP 替身子进程；输入混合 LF/CRLF 的 UTF-8 中文证据，预算 3、任务 1、并发 1 | 退出 0；协调、分析、汇总共 3 次，3 份 agent 记录；`execution_status=succeeded`、`analysis_status=advisory`；证据字节及 SHA-256 一致。重用输出目录退出 5，省略预算退出 2。真实模型调用数为 0，不能据此证明模型协作质量。记录同上。 |
| Burp JAR 构建及调度回归通过 | 亲自执行 `gradlew.bat check jar --no-daemon --console=plain`，检查 JAR 内容及 manifest | 退出 0；`BUILD SUCCESSFUL in 33s`，`schedulerRegressionTest` 执行。JAR 515261 字节，含 Gson、RE2J、NanoHTTPD；Montoya 为 compile-only；组件版本 2.0.0。SHA-256 为 `b9322e4f166103c87396e0b15afcbeade02a9fc1880d6c91e5108fde2e321952`。原始记录为 `validation/burp-build.log`。编译存在既有弃用警告。尚未验证 Burp GUI 加载。 |
| 合并后的基础 main 已有 CI 证据 | 上一轮核查 [main CI 38426039071](https://github.com/2233admin/reverse-skill-evolver/actions/runs/38426039071) 的实际日志 | 对象为 main `39d1d19`：Linux Python 364 passed、44 skipped，Java check 和两个 POSIX 构建成功；这是基础 main 的记录，不能当作本发布包在 Linux 上的安装验收。 |

## 验收条件对应

本事项没有另行成文的验收条件；上表分别记录构建、安装入口、受控运行及基础 CI 的证据。

## 证据缺口

- 真实 OMP 模型的蜂群 JSON 遵循、并行分析质量和费用表现未验。按 [测试指南](BETA-TEST.md) 使用自己批准发送的证据及已配置模型验证。
- 真实用户首次安装、Linux/macOS 安装包入口、OMP skill 自动发现、Burp GUI、设备/远端同步未验，需要在对应客户端实际执行。
- IDA 测试仍要求已安装并许可的 IDA/idalib 与可用服务；未据此承诺任意目标兼容性。

发布后以 Release 中的 `SHA256SUMS.txt` 核对下载文件。这里的执行成功只支持已覆盖路径，模型结论保持 advisory。
