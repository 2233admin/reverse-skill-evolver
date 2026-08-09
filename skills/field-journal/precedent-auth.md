# 当前 Session 授权合同

本文件不授予任何目标权限，也不能替代当前 session 的用户授权。

安全相关 route 只接受 `route_task.py` 识别的显式 `authorization_scope`：

- `ctf`
- `own_asset`
- `lab_fixture`
- `bug_bounty`
- `engagement`

目标名称、路径、包安装状态、历史执行记录、precedent 文件或另一个 session 的结论，都不能推导出当前授权。

当授权范围缺失、含糊或与请求动作不匹配时，route 必须保持 `blocked`，且不得执行受控入口。目标专属的 Rules of Engagement、凭据与运行证据应保存在仓库外的当前 session 工作面中，不得写入本通用 skill 包。

`precedent-reverse.md` 与 `precedent-pentest.md` 仅提供脱敏的通用方法参考；它们不改变当前 route 的授权判定。
