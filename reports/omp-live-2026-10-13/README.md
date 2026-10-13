# #21 真实 OMP 验证

授权：[21-D1 回执](https://github.com/2233admin/reverse-skill-evolver/issues/21#issuecomment-6144393049)，用户随后提供新 MiniMax API 和 FuturePPO 的 GLM/DeepSeek 备用。凭据只从本轮进程环境读取，不包含在此目录中。总上限 37 次逻辑 OMP 调用，单次 60 秒；物理 provider 请求和费用未知。每个候选保持 not_promoted。

## 第一轮，默认 provider

`run-live.py` 通过真实 `python -m reverse_skill --json evolve ... --max-evaluations 3 --max-reflections 1 --model-timeout 60` 运行固定 12-case suite。源提交 8a0ca33。OMP 18.8.9，config.yml 哈希见 run-metadata.json。首条请求收到 **402 Insufficient Balance**，退出码 5；1 次逻辑调用，成功响应 0。full-suite/results.json 保留冻结 catalog/fixtures/候选和失败位置、进程 stderr；status=incomplete，无评分或晋级。

## 第二轮，显式 MiniMax 与新 API

`run-pinned.py --model minimax-code-cn/MiniMax-M3.1-Flash-Preview --name full-suite-minimax` 调用同一个公开 `reverse_skill.cli.main`，仅在 OMP 进程边界追加模型/API key/本轮 retry overlay 并设置累计调用上限；响应没有替换或模拟。API key 来自 REVERSE_TEST_API_KEY，记录的 CLI argv 不包含凭据。overlay 将 maxRetries=0、fallbackChains={}；仍不承诺其他兼容重试的物理请求数。

实际首条响应 `{"route_id": "apk-android"}` 完整解析并通过路由 oracle。第二次调用在 Windows TemporaryDirectory 清理时遇到 WinError 32，导致整轮失败；已完成首条原响应留在 full-suite-minimax/results.json，status=incomplete，不将它作为全套比较结果。累计转发调用 3/37，第二条响应未能由旧实现返回，结果未知。

复现与修复：真实隔离 Python 子进程持有自建临时 cwd，证明旧 cleanup 会掩盖已经取得的模型响应。_omp 现在使用 TemporaryDirectory(ignore_cleanup_errors=True)，目录被锁时仍保留模型响应/原模型错误；目录可能暂留系统临时区域直到持有者释放，不终止未知共享进程。`python -m pytest tests/test_evolution_contracts.py tests/test_evolution_optimizer.py -q --tb=short` → **95 passed**，包括真实隔离 cwd 锁检查。

## 完整真实套件与受控反思

修复后源提交 **81c7de3**，实际使用 OMP **18.8.9**、`minimax-code-cn/MiniMax-M3.1-Flash-Preview` 与用户的新 API。每次调用最多 60 秒，重试 overlay 仅作用本轮进程；宿主配置哈希及完整 CLI argv 见各 metadata.json。配置/候选/稳定 skills 未覆盖。

`full-suite-minimax-fixed`：**24 次逻辑 OMP 调用，84.473 秒，CLI 退出码 0**。baseline 和 curated 各完成全部 **12/12** case，均通过 **12/12**，无 invalid response。覆盖固定套件的 10 个 track；两者各 track 全通过。termination=`all_frontier_candidates_passed`，evaluations_consumed=2、reflections_consumed=0。真实 stdout 是整段 JSON 路由答案，严格 whole-answer parser 接受；没有以模型叙述代替 oracle。此完整套件提前停止，因此本轮没有覆盖反思路径。

为补反思路径，在独立 `controlled-reflection` 目录对一条 APK 用例使用刻意 abstain 的候选（controlled-failing-candidate.md），复用同一 frozen catalog。**4 次真实逻辑调用，14.187 秒，CLI 退出码 0**：baseline **1/1**，受控 curated **0/1**，一次真实 reflection 后 proposal **1/1**；3 次完整单例评估、1 次反思，termination=`budget_reached`。原 reflection 输出、上下文、祖先文本/哈希及 parent lineage 均保留。这是受控单例反思诊断，不与完整 12-case suite 作可晋级比较。

全批累计 **31/37** 次转发逻辑 OMP 调用：默认 provider 失败 1、cleanup 失败的 MiniMax 首轮 2、完整套件 24、受控反思 4。budget.json 中 blocked_calls=0。物理请求、tokens、费用无法从当前 print 响应可靠取得，保持 unknown，不按模型价目推算账单；默认 provider 的实际身份未从失败响应独立确认。GLM/DeepSeek 备用本轮未调用。

验证：逐个核对两个成功 envelope 与 results.json 相等；每个输入及 candidate artifact 的 SHA-256 与报告相符；每个完整 candidate 均覆盖该次 suite 的全部 fixture；每个实际原始响应重新经严格 parser 得到同一 route/invalid；partial run 不含虚假评分；全部保持 not_promoted。凭据扫描通过，日志和报告不含提供的 API key。失败的真实默认 provider 请求及 Windows cleanup 中断证明 incomplete 路径，没有伪造完整结果。

Git 字节保真：此目录在 .gitattributes 设为 `-text`，冻结 artifact 不经过自动换行转换。重新加入后，直接取当前 Git index/blob 中的输入与候选字节核对报告 SHA-256，全部一致；工作区核对不能单独替代该检查。

可审阅结论：#21 要求的真实完整路由 suite、真实 framing、失败归档与独立有界反思已取得证据；下游逆向任务、真实攻击、长期模型质量和晋级均不由此次结果证明。下一责任人：审阅者，审阅 Draft PR #42；稳定候选仍需独立全套比较与人工审阅。
