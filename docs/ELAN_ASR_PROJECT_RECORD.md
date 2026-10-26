# ELAN 中文课堂转录辅助工具项目总记录

更新日期：2026年10月26日。用途：记录构建问题、修复合并、Linux 实际识别验收、ChatGPT 个人技能及调用方式。当前结果是可运行的转录辅助环境；真实课堂最终标注仍按实际音视频复核。

## 一、已合并变更

| 仓库与PR | 内容 | 合并提交 |
| --- | --- | --- |
| [hello-world #2](https://github.com/mteasy1-code/hello-world/pull/2) | 完整离线 Faster Whisper 运行时、JSON/SRT/EAF导出、whisper.cpp实际识别与归档验证 | `7302e293c5f51421c5af4fa2c089d0c42a5ca83c` |
| [snake-battle-stable-demo #1](https://github.com/mteasy1-code/snake-battle-stable-demo/pull/1) | 修复旧二进制地址404、校验模型、中文短音频与迁移后复测 | `4b8f9de081dc9349a1032f491a84c1222ae68b03` |
| [hello-world #3](https://github.com/mteasy1-code/hello-world/pull/3) | 增加240 MiB分卷，解决ChatGPT连接器512 MiB单次下载限制 | `65715c6cd79708cecb90eb2e8028b8701e6dcdb1` |

上述合并由仓库所有者在对话中授权。原有工作流、修复分支与历史提交均保留，未删除项目文件。首次修复已存在的 `b5454` 地址在本次检查时确已构建成功，本次进一步补齐了功能验收。

旧便携运行时 `faster-whisper==1.2.0` 在导入时缺少 `requests`：该版本使用了未直接声明的依赖；新运行时采用1.2.1，并明确固定 `requests==2.32.5`、`huggingface-hub==0.36.0`。原Python3.13 wheel下载工作流保留，单独下载wheel不等同于识别功能验收。

## 二、验收结果

| 验收阶段 | 运行或记录 | 结果 |
| --- | --- | --- |
| 原修复分支完整运行时 | [40308614011](https://github.com/mteasy1-code/hello-world/actions/runs/40308614011) | 构建、迁移、Ubuntu22.04/24.04全部通过 |
| 分卷兼容分支 | [40313876223](https://github.com/mteasy1-code/hello-world/actions/runs/40313876223) | 三分卷生成、两系统离线复测全部通过 |
| 合并后主分支完整运行时 | [40314476987](https://github.com/mteasy1-code/hello-world/actions/runs/40314476987) | 构建、Ubuntu22.04/24.04全部通过 |
| hello-world 主分支 whisper.cpp | [40313449653](https://github.com/mteasy1-code/hello-world/actions/runs/40313449653) | 中文推理、JSON/SRT时间戳、解包后再次推理通过 |
| snake-battle 主分支 whisper.cpp | [40313459986](https://github.com/mteasy1-code/snake-battle-stable-demo/actions/runs/40313459986) | 同上，全部通过 |
| 当前ChatGPT对话内安装 | [安装验证记录](validation/2026-10-26-installation.json) | 连接器下载三卷、逐层SHA256、7,644项清单、依赖检查及离线推理通过 |
| 独立技能调用 | [调用验证记录](validation/2026-10-26-skill-invocation.json)、[执行记录](validation/2026-10-26-execution.json) | 按技能说明实际执行，输出JSON/SRT/EAF；推理前后各两次严格清单检查通过 |

对话端测试发现同步工作区可能出现模型或动态库临时文件与短暂权限变化，严格校验曾拦截该状态。失败缓存保留，未忽略额外文件或修改可信清单。最终从可信分卷安装到独立 `/tmp` 缓存后通过；技能默认使用该类缓存目录。安装器最多进行5次完整检查，要求连续两次严格匹配；持续失败即停止。

## 三、运行时与模型

- Linux x86_64、CPU int8；已测Ubuntu22.04、24.04，以及本次对话的Linux执行环境。
- 便携CPython3.11.14、Faster Whisper1.2.1、CTranslate2、PyAV、ONNX Runtime、tokenizers等完整依赖。实际完整版本见包内 `verification/requirements.lock.txt`。
- 模型：`Systran/faster-whisper-small`，本次对话验收修订号 `536b0662742c02347bc0e980a01041f333bce120`。
- 对话安装来源提交：`eaed632e5268c852408954b0037d145787824898`；合并后默认分支对应代码为 `65715c6cd79708cecb90eb2e8028b8701e6dcdb1`。
- 本次对话重组归档SHA256：`3595416f3ae65ce000502e5868a6fbd47105341a302de0317894821f3758385b`。不同构建的归档值可能不同，必须读取所选运行的实际元数据。

短音频为FunASR公共示例，时长5.5466875秒。实际识别结果为“欢迎大家来体验打磨院推出的语音识别模型”，1段、18个词级时间戳；独立调用的段落范围为560–5040毫秒。标准参考文本中的“达摩院”有2字误识别，19字字符错误率为10.53%。该值仅描述这个示例。

## 四、在ChatGPT对话中调用

个人技能显示名：**ELAN 中文课堂转录**；技能名：`elan-classroom-asr`。技能已完成格式校验、实际安装测试及独立调用测试，并保存至个人技能。保存提交为 `442c98250454942e92d925fab8e27fbfe9bc8a18`；系统保存后会将目录规范化，后续维护应按技能名定位现有技能。

在支持个人技能和Linux执行环境的ChatGPT Work对话中，从技能列表选择该技能，再提供实际音视频。可使用如下指令：

```text
使用 $elan-classroom-asr 处理我提供的中文课堂音视频，核对时间戳，输出 EAF、SRT、JSON 和验证记录。已有 EAF 时保留原件并另存修订版。
```

也可在支持的输入框中输入 `@`，选择“ELAN 中文课堂转录”。若列表未刷新，新开Work对话后重新选择。技能保存和加载与Linux执行能力是两个条件；没有文件访问或执行环境的普通聊天不能据此承诺后台运行这些程序。

技能负责查询已成功验收的工作流、获取三个分卷、校验并重组、安装或核对缓存、执行本地识别及输出验证。媒体在当前获授权环境处理，不需要上传到公开GitHub仓库。

## 五、使用边界

自动EAF只有 `ASR_待分人` 初稿轨道，不虚构教师或学生身份。教师T、学生S1/S2等、不同内容的重叠轨道，以及齐读、错峰齐读、齐答、错峰齐答，需要结合实际课堂证据核对。现有环境没有经过验证的说话人聚类、声源分离或强制对齐；ECAPA模型下载成功不能替代这些验收。

时间戳检查覆盖非负、顺序、媒体边界及JSON/SRT/EAF一致性，没有量化相对于人工声学标注的误差。本次短样例不代表整节课堂逐字准确率或分人精度。未人工听校的输出必须作为ASR初稿交付。

## 六、产物与维护

[工作流与最新产物入口](https://github.com/mteasy1-code/hello-world/actions/workflows/elan-asr-verified.yml)。完整包供用户直接下载；技能使用同一次成功运行的 `elan-asr-runtime-part-00`、`01`、`02` 三个独立产物，每卷最多240 MiB。不能只取一卷，也不能混用不同运行的分卷。

产物保留30天，临时下载链接不可作为永久配置。后续调用应重新查询未过期的成功运行；没有可用产物时重新触发并验收构建，权限或平台时限受限时明确说明阻塞点。项目工作流和个人技能已保存，不依赖当前对话的临时目录长期存在。

后续重大变更和默认分支合并遵循用户当次授权。需要回滚时撤销对应合并提交或恢复个人技能历史版本，保留历史文件；不要通过删除项目文件来回滚。

附录JSON中的环境绝对路径已统一为 `<WORKSPACE>`、`<RUNTIME>` 等占位符；源提交、模型修订、文件摘要、输出内容与实际测试状态保持原值。
