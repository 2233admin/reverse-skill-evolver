# [2026-07-11] 私有 API 逆向方法论：CDP 抓包 + 前端源码交叉验证 + 实测校准

**记忆层级**: candidate（新鲜单次会话方法论提炼，尚未经过回归/多案例验证，只能提示，不得自动驱动路由 —— 见 `../../evolution/SKILL.md` 的记忆分层规则）

## 场景分类
私有 API 逆向（CDP 抓包取证 + 前端源码交叉验证）—— 本条目是从一次具体目标的会话中剥离出的通用方法论，不绑定单一目标平台。

## 目标概述
从"逆向某目标 Web 应用的一个私有数据接口"这类具体任务里，提炼出一套可复用的方法论：优先用目标自身前端 JS 里的表格/字段定义文件确定字段语义，再用真实探测结果校准，而不是仅凭抓包猜字段含义、也不盲信源码推断出的响应结构。

## 完整执行链路

1. 用浏览器 CDP 抓包，定位目标私有数据面板触发的具体请求（URL 特征、请求方法、关键参数）
2. 在 Network 面板用 initiator 回溯，找到发起该请求的前端脚本，缩小搜索范围
3. 在目标应用自身的前端 JS 里搜索"表格/网格列定义"文件（形如 `*_grid_columns.js`/`*_table_def.js` 一类的列名→字段定义映射文件）—— 很多数据面板会把列名到业务语义的映射写死在这类文件里，这是比逐字段猜测网络包字段名更高信号的来源
4. 用该定义文件建立"列名 → 语义"假设表（hypothesis map），标注每个字段的业务含义、单位、预期类型、预期顺序
5. 对真实端点发起一次实际探测（live probe），拿到真实响应
6. 把真实响应结构与第 4 步的假设表逐项 DIFF：结果集（ResultSets）个数是否一致、key 顺序是否一致、字符串 vs 数字类型是否一致、行的排序方向是否一致、请求是否需要特定 Header
7. 记录所有偏差，把假设表更新成"已验证的真实契约"，并在解析代码里显式写出每个偏差点的处理逻辑，不要藏在无注释的特殊分支里
8. 编写解析器：按"列名 → 下标"的映射取值，而不是按固定列序假设；当响应里同时出现多个结果集时，按"是否包含预期标记列名"选中目标结果集，而不是固定用下标 0
9. 补一个"打乱列顺序"的单元测试，断言解析器仍然按列名正确取值 —— 即使当前观察到的顺序恰好和预期一致，这个测试目前没抓到真实 bug，但成本很低，属于保险性质
10. 对必填/关键字段做"缺失或类型不符就直接返回 Err"的防御，不使用静默 fallback 到 0/null，尤其是新接入、尚未经过实战检验的数据源

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 只凭网络包猜字段含义，容易猜错业务语义 | 网络层字段名通常是精简、无语义的短 key，和业务概念不是一一对应 | 先搜目标前端自身的表格列定义 JS，把"列名 → 语义"映射当作权威来源，网络包只用来定位请求本身 | - |
| 假设"结果集只有一个数组/固定在下标 0" | 服务端返回结构可能包含多个 result set（例如分页元信息 + 数据 + 汇总），且数组顺序不保证稳定 | 按"是否包含预期特征列名"来选中目标数组，而不是写死下标；本次实测发现是两个 `ResultSets`，靠检查是否存在 `"rq"` 这个列名区分出正确的那个 | - |
| 本地解析器按 JS 源码里列出现的顺序硬编码下标 | 把"当前观察到的顺序"当成契约，而不是把列名本身当契约 | 解析前先读响应自带的列名/字段名数组，建 ColName→index 映射，取值时查这个映射，不查固定位置 | - |
| 数字字段解析报类型错误 | 假设字段值是字符串（需要额外 parse），但真实响应给的是 JSON number | 解析层对每个字段做类型自适应（先判断实际 JSON 类型再转换），不要写死"一定是字符串再 parse" | - |
| 日期字段格式/排序逻辑跑出来是错的 | 源码/文档暗示日期是紧凑数字格式，实测是带分隔符格式（如 dash 分隔）；同时假设行按时间正序，实测是逆序（最新在前） | 用真实探测样本反推真实格式和真实排序方向，源码/文档描述只作为初始假设，不能直接当真值使用 | - |
| 请求被拒绝/参数不生效 | 照抄 DevTools 里看到的完整请求头集合，实际很多是浏览器自动带的，不是接口强制要求的 | 从最小请求头集合开始尝试，逐步加，用真实探测确认哪些头是必须的（本次实测发现连 `User-Agent` 都不是必须的） | - |

## 工具链发现

- Chrome DevTools 的 Network 面板 + initiator 回溯，是定位"哪个脚本发起了这个私有请求"最快的路径，比全文搜索前端源码更精确
- 目标应用自身的前端表格/网格列定义 JS（column-definition file）往往是一份免费的"半官方字段字典"，可信度高于逆向猜测，应该作为字段语义的第一手来源
- 一次真实探测（live probe）胜过十次读源码推断 —— 源码只能证明"作者曾经想这样设计"，不能证明"线上环境现在真的这样返回"；凡是源码/文档推断出的响应结构，都只是待验证的假设
- 单元测试里加一个"打乱列顺序"的 fixture，是防止"按位置取值"回归的低成本保险，即使当前没抓到真实 bug 也值得写

## 关键代码/命令

```text
# 契约校准 checklist（实测优先于书面/推断规格）
[ ] 1. 从前端源码/文档得到"假设契约"（字段名、类型、顺序、结果集个数）
[ ] 2. 对真实端点发起最小化真实请求，拿到真实响应
[ ] 3. 逐项 DIFF：结果集个数 / key 顺序 / 类型(string vs number) / 排序方向 / 必需请求头
[ ] 4. 把所有偏差写成显式规则，禁止"看起来能跑就不管了"
```

```text
# 解析器骨架（伪代码，按列名而非位置取值）
function parse_row(row, column_names):
    index_of = { name: i for i, name in enumerate(column_names) }
    if "expected_marker_column" not in index_of:
        raise Error("this result set does not match expected shape")
        # 而不是默认取 result_sets[0]

    def field(name):
        if name not in index_of:
            raise Error(f"missing required field: {name}")
            # fail loudly，不静默 fallback 成 0/null
        raw = row[index_of[name]]
        return coerce_by_actual_json_type(raw)
        # 先看真实 JSON 类型再转换，不假设一定是字符串

    return Record(
        date  = field("date_col"),   # 用真实探测确认真实格式后再决定要不要标准化
        value = field("value_col"),
    )

# 回归保险：打乱列顺序仍应解析正确
test("parser is order-independent"):
    scrambled_columns = shuffle(real_column_names)
    scrambled_row = reorder(real_row, scrambled_columns)
    assert parse_row(scrambled_row, scrambled_columns) == parse_row(real_row, real_column_names)
```

## 对本包的改进建议

1. `skills/js-reverse/SKILL.md` 应该把"实测优先于书面/推断规格（live probe overrides written/inferred spec）"和"按列名而非位置解析（parse by column name, never by position）"明确写成 house principle，而不是只停留在隐性习惯上 —— 本次已在该文件里补了一节落实此建议（见 workstream C3 改动）。
2. `skills/js-reverse/SKILL.md` 的 CDP 工具映射表目前只列了 `js-reverse_*`/`jshookmcp` 两套命名，缺了 `mcp__plugin_ecc_chrome-devtools__*`（Chrome DevTools MCP 插件，提供 `evaluate_script`/`list_network_requests`/`click`/`navigate_page`/`take_screenshot` 等工具）—— 这正是本次会话实际可用并用来完成 CDP 抓包取证的工具面，和现有两套是平行关系，不是替代关系，应该补充进映射表（同上，已在 workstream C3 里补充）。

## 可复用的模式/脚本片段

**私有数据接口逆向标准流程（通用）**：
```text
1. CDP 抓包定位目标请求
2. 前端源码/表格列定义文件找字段语义假设
3. 真实探测校准，DIFF 出所有偏差
4. 按列名建索引，禁止按位置解析
5. 打乱列序单测兜底
6. 关键字段缺失/类型不符直接 Err，不静默降级
```

**契约偏差常见模式**：
```text
- 结果集个数比文档/源码暗示的多 → 按标记列选，不按下标选
- key 顺序不稳定 → 永远用列名索引
- 数字字段实际是 JSON number 而非字符串 → 按实际类型解析，不假设
- 排序方向和源码/文档暗示相反 → 真实样本校准排序
- 请求头比想象中少 → 从最小集合开始加，逐步验证
```

## 进化动作
- [ ] 未更新路由矩阵（routing.md/routing.json）—— 本条目是方法论层面的补充，不改变宏观路由决策
- [ ] 未更新 bootstrap-manifest —— 未引入新工具依赖
- [x] 更新了子 skill 文档 —— 见 `../../js-reverse/SKILL.md` 新增的 CDP 工具面小节（`mcp__plugin_ecc_chrome-devtools__*`），该小节引用本文件作为方法论溯源记录

## 环境信息
- OS: Windows
- 工具版本: Chrome DevTools（CDP），`mcp__plugin_ecc_chrome-devtools__*` MCP 插件
- 目标平台: 通用私有 Web 数据接口（本条目基于一次真实会话泛化提炼，不针对单一目标平台）

## 脱敏要求
本条目为泛化方法论总结，基于一次真实逆向会话提炼，已剥离具体目标域名/接口路径/字段原文等真实特征，仅保留可复用的模式描述，不涉及可识别的真实目标。

---
<!-- [进化统计] 本包累计完成项目: 1 | 本次新增模式: 1 | 本次修复工具链问题: 0 -->
<!-- [社区贡献] candidate 层级条目，暂不满足 promotion gate（未经回归/多案例验证），见 CONTRIBUTE-BACK.md -->
