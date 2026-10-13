# #21 真实 OMP 验证

授权：[21-D1 回执](https://github.com/2233admin/reverse-skill-evolver/issues/21#issuecomment-6144393049)，用户随后提供新 MiniMax API 和 FuturePPO 的 GLM/DeepSeek 备用。凭据只从本轮进程环境读取，不包含在此目录中。总上限 37 次逻辑 OMP 调用，单次 60 秒；物理 provider 请求和费用未知。每个候选保持 not_promoted。

## 第一轮，默认 provider

`run-live.py` 通过真实 `python -m reverse_skill --json evolve ... --max-evaluations 3 --max-reflections 1 --model-timeout 60` 运行固定 12-case suite。源提交 8a0ca33。OMP 18.8.9，config.yml 哈希见 run-metadata.json。首条请求收到 **402 Insufficient Balance**，退出码 5；1 次逻辑调用，成功响应 0。full-suite/results.json 保留冻结 catalog/fixtures/候选和失败位置、进程 stderr；status=incomplete，无评分或晋级。

## 第二轮，显式 MiniMax 与新 API

`run-pinned.py --model minimax-code-cn/MiniMax-M3.1-Flash-Preview --name full-suite-minimax` 调用同一个公开 `reverse_skill.cli.main`，仅在 OMP 进程边界追加模型/API key/本轮 retry overlay 并设置累计调用上限；响应没有替换或模拟。API key 来自 REVERSE_TEST_API_KEY，记录的 CLI argv 不包含凭据。overlay 将 maxRetries=0、fallbackChains={}；仍不承诺其他兼容重试的物理请求数。

实际首条响应 `{"route_id": "apk-android"}` 完整解析并通过路由 oracle。第二次调用在 Windows TemporaryDirectory 清理时遇到 WinError 32，导致整轮失败；已完成首条原响应留在 full-suite-minimax/results.json，status=incomplete，不将它作为全套比较结果。累计转发调用 3/37，第二条响应未能由旧实现返回，结果未知。

复现与修复：真实隔离 Python 子进程持有自建临时 cwd，证明旧 cleanup 会掩盖已经取得的模型响应。_omp 现在使用 TemporaryDirectory(ignore_cleanup_errors=True)，目录被锁时仍保留模型响应/原模型错误；目录可能暂留系统临时区域直到持有者释放，不终止未知共享进程。`python -m pytest tests/test_evolution_contracts.py tests/test_evolution_optimizer.py -q --tb=short` → **95 passed**，包括真实隔离 cwd 锁检查。

下一步：以修复后的代码继续新 output 目录的真实 MiniMax suite，在 budget.json 的累计上限内运行；必要时使用用户提供的备用模型。此记录不是完整 #21 验收结论。
