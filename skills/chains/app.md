# chains-app 决策骨架（场景→判据→转向）

> 形式借鉴 ARTEX `agent/chainskel/`（AGPL-3.0）的决策骨架结构；**本文内容全部蒸馏自本包
> `skills/field-journal/` 自有种子，未复制 ARTEX 任何文本。** 每行末尾标注来源条目。

## 一、移动端环境与注入

- 场景:准备动态分析环境|判据:Frida server 未启动或端口被占是首要失败点；App 启动快于注入则 hook 不生效|转向:先 `adb forward` + 起 server；hook 用 `-f` spawn 模式配 `--no-pause`；起不来先 `frida-ps -U` 确认能列出进程〔seed-008〕
- 场景:App 检测到 Frida 后退出|判据:自检 frida-server 端口或默认路径/字符串|转向:改名 + 换端口（`-l 0.0.0.0:1234`，客户端 `-H`）；再不行换 frida-gadget 注入或 zygisk 隐藏〔seed-008〕〔seed-009〕
- 场景:App 启动前就检测，hook 来不及|判据:检测在 `+load` 或 constructor 中执行|转向:spawn 模式 + `--aux 'spawn=1'`，必须在进程创建前拦住〔seed-009〕

## 二、证书校验绕过

- 场景:抓包报证书错误|判据:报错类型区分 CertPin / Hostname / TrustManager，决定 hook 点|转向:先 objection 一键 `sslpinning disable`（覆盖约 80%）；不生效再用覆盖更广的脚本；最后才手写 hook〔seed-008〕
- 场景:hook 后部分请求仍 SSL 错误|判据:应用混用 OkHttp 与原生 HttpsURLConnection|转向:补齐 `X509TrustManager.checkServerTrusted` 与 `HostnameVerifier.verify` 两个点〔seed-008〕
- 场景:绕过后仍闪退|判据:SSL Pinning 与越狱/root 检测同时启用|转向:两个模块同时开，不要只解一个〔seed-009〕
- 场景:装完证书仍报错（iOS）|判据:iOS 14+ 系统证书需在"证书信任设置"二次开启|转向:装证书后去信任设置勾选，漏这一步会误判为 Pinning 问题〔seed-009〕

## 三、代码定位

- 场景:类名找不到|判据:ProGuard 混淆后类名变短名，直接搜无结果|转向:用 `Find Usages` 反查谁实例化了目标类（如 OkHttpClient.Builder），顺藤摸瓜〔seed-008〕
- 场景:需找 native 实现|判据:Java 层逻辑指向 so 库|转向:先 grep 加载点（loadLibrary/load），再进 so 找 JNI_OnLoad，区分静态/动态注册〔precedent-reverse〕
- 场景:通用类库型加固或不常见运行时|判据:标准工具链无输出（不同意 dex 结构 / 非常规运行时）|转向:先 dump 内存中的 dex 再反编译；特定运行时用其专用解析工具〔precedent-reverse〕

## 四、验证与收尾

- 场景:声称绕过成功|判据:必须看到明文流量，而非"脚本无报错"|转向:重新抓包确认明文；未见到实据则降级为 candidate〔seed-008〕
- 场景:修改后无法复现原始行为|判据:无对照基线|转向:保留改动前的现象记录（错误类型、调用栈）作为对照证据〔seed-009〕

## 五、Unity IL2CPP 游戏

- 场景:判断是否 IL2CPP|判据:库目录下存在 `libil2cpp.so`，且 Managed 目录有 `global-metadata.dat`|转向:确认后走元数据还原路径，不要直接啃 so〔seed-014〕
- 场景:还原方法名与结构|判据:元数据 + so 需配对使用|转向:用 dump 工具还原出符号表与结构描述，再把描述导入反编译器的 IL2CPP 脚本〔seed-014〕
- 场景:定位关键业务逻辑|判据:还原出的符号表可按业务关键词检索|转向:在 dump 出的伪源码中按业务词搜（购买/校验/签名/VIP 判定），拿到偏移再去反汇编确认〔seed-014〕
- 场景:元数据被加密|判据:标准 dump 工具报格式不支持|转向:在文件读取处挂钩，于内存中已解密后 dump 出元数据，再喂给 dump 工具〔seed-014〕
- 场景:符号表与二进制不匹配|判据:dump 产物与目标 so 非同一次采集|转向:必须用同一次 dump 的成套产物；换分析工具时清缓存〔seed-014〕
- 场景:动态 hook 该类型方法报错|判据:IL2CPP 方法非标准运行时方法，需按方法偏移寻址|转向:使用 IL2CPP 专用 hook 桥接库，不要硬写通用拦截〔seed-014〕
- 场景:选择静态 patch 还是动态 hook|判据:目标是否校验文件自身完整性|转向:有完整性校验则优先 hook 不改文件；无校验可静态 patch〔seed-014〕
- 场景:patch 后启动崩溃|判据:存在哈希或防篡改校验|转向:一并处理校验逻辑，或退回 hook 方案〔seed-014〕
- 场景:重打包后启动崩溃|判据:签名方案 v2 不允许改字节后再签|转向:删旧签名目录 → 重打包 → 重新签名一气完成〔seed-014〕

---

## 溯源

| 来源条目 | 贡献内容 |
|---|---|
| `seed-008_apk-okhttp-ssl-pin-bypass.md` | Android 环境、Frida 反检测、证书绕过三层策略、混淆类定位、验证标准 |
| `seed-009_ios-jailbreak-detect-bypass.md` | iOS 越狱检测、constructor 时机、双重防护叠加、证书信任设置陷阱 |
| `precedent-reverse.md` | native 定位、加固与非常规运行时处理 |
| `seed-014_unity-il2cpp-reverse.md` | IL2CPP 判定、元数据还原与配对、加密元数据处理、hook 与 patch 的取舍、重打包签名 |
