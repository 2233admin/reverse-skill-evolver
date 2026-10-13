# PR #42 原生 helper 兼容性检查

正式 Codex 审阅 [4260469760](https://github.com/2233admin/reverse-skill-evolver/pull/42#discussion_r4260469760) 指出基础 namespace 守卫遗漏所选操作的依赖。根会话在用户已批准的反馈处理范围内复现：缺失/不可调用的 callees、ida_bytes.get_bytes、pseudocode 或 xrefs_to 会在枚举开始后抛原始 KeyError/TypeError。

新增八种缺失/不可调用负例在原 38379a7 上 **8 failed、15 deselected，0.17秒**。修正将所选操作的 callable 依赖传给共享源检查：快照检查 callees、启用字节捕获时的 ida_bytes.get_bytes、启用伪代码捕获时的 pseudocode；初筛检查 xrefs_to。错误明确指出缺失 helper 和打开原生 owned database 后传 exec globals 的恢复动作，发生在函数/字符串/导入枚举之前。

另外验证不用的 helper 不被要求：关闭字节/伪代码捕获的快照不依赖 ida_bytes、pseudocode 或 xrefs_to；初筛不依赖 callees、字节模块或伪代码。

`python -m pytest tests/test_omp_analysis.py tests/test_omp_binary_diff.py tests/test_omp_hook_plan.py tests/test_omp_signature_replay.py tests/test_omp_skill_contract.py -q -p no:cacheprovider --tb=short`：**65 passed、0.44秒，退出码0**；diff check通过。没有新增模型、真实 IDA/Frida、安装、配置或数据库操作；原真实样例归档仍只覆盖记录中的旧源码/环境，不能据本次替身检查扩展样例范围。
