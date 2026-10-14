# 实现决定

## 安装与恢复

Bash 的条件调用会禁用嵌套函数的 errexit；因此安装、下载、解包和复制操作显式返回非零，jadx 在 ready 前执行版本检查。主循环仍收集所有能力结果，出现失败时最终退出 1。下载目录由 mktemp 独占，清理只针对该目录。

Windows apktool 下载使用唯一临时兄弟文件。标准库 ZIP 检查验证 manifest/main class，下载完成后检查资产长度（若元数据提供）及 Java 版本命令（15 秒上限），再使用同目录 File.Move/File.Replace 发布。finally 删除本调用的临时文件并关闭本调用的 Java 进程。健康安装直接返回。发现逻辑拒绝不完整的托管 JAR，包含关联的旧 wrapper，避免遗留坏包阻止修复。

使用现有 .NET/Python/Bash 工具即可完成；不引入安装库，因为外部库不能简化这几个已有脚本的本地事务边界。

## 本地开销

- 工具快照只存在于一次 refresh，下一次重新发现并执行版本命令。
- 两个文件名集合采用 OrdinalIgnoreCase；原有数组仍控制碰撞、复制和输出顺序。
- 邮件扫描先枚举最大局部串，只有后面紧跟 @ 才尝试原邮件模式。边界搜索限制在当前局部串；原 Unicode 单词边界、domain allowlist 和脱敏输出保持。
- 报告边界通过 regex.search(text, pos) 查找，仅切出返回 section。
- 路由 `_TaskText` 只在一次 plan 中存活，compact 文本按需计算；公开 contains_keyword 保持语义，ASR 优先、override 和只读 preflight 不变。
- output.py 保存既有 envelope/human/emit；cli 继续导出原兼容入口。ASR 客户端保留已使用的构造注入边界，真正实现只在网络命令执行时导入；KINDS 统一来源。

## launcher

运行时 source/manifest/Python signature 和目录所有权检查保留。健康运行只启动一个 `-I -X utf8` Python：先导入所需依赖和 CLI，再执行 main，保留调用者 cwd/Unicode argv/退出码。健康检查仍覆盖 HTTPX。

每次调用有独占临时信号目录。只有 bootstrap 的导入块捕获 ImportError 并写信号；callback 在该块之外，退出 86 或执行时 ImportError 均不能触发修复。首次信号允许一次 pip 修复，再失败返回原 output-v1 runtime 错误信封。信号与子进程退出码同时核对，避免把命令退出码当作健康失败。

## 所有权缺口

现有 `tests/test_powershell_scripts.py` 的 jar_only 构建测试使用零字节 JAR；新的完整性检查会拒绝它，两个 PowerShell 引擎的旧夹具因而失败。这是已授权“半成品不得 available”的预期变化，不降低验证规则。该测试不在 #56 写入清单内；最小后续决定是父级分配夹具更新所有权，将空文件替换为带 manifest/main class 的合成 ZIP/JAR。当前在允许的测试文件中补同一构建入口及正确夹具验证，保留这两个原失败供审查。
