# 持久化恢复

[English](RECOVERY.md) | 简体中文 · [项目首页](../README.zh-CN.md)

## 本地应用

示例环境选择 `SMARTCOURSE_PPT_GENERATOR=qwen`，使用现有 CourseStructureAgent 调用配置的 Qwen 接口，生成可编辑的标题与正文型课件及逐页讲稿，再翻译该源课件。生成内容和排版需要审阅。可选的 `deeppresenter` 设置依赖单独的 PPTAgent 运行目录，该目录在 10 月 22 日的重建实例中缺失，本次测试使用 Qwen 生成入口。

1. 克隆仓库，复制 `.env.example` 为 `.env`，将运行目录设置到可写的持久化磁盘。
2. 安装 Python 3.13、Node.js、FFmpeg 和 LibreOffice。执行 `bash scripts/setup-local.sh`。
3. 设置参考音频、参考照片、Whisper small 模型及 CJK 字体路径。参考素材由使用者提供，公开仓库不含个人素材。
4. 执行 `bash scripts/start-local.sh`，浏览器访问 `http://127.0.0.1:18770`。应用数据、产物和日志均保存在运行目录。

## 华为云 Ascend 910B

当前验证组合为 PyTorch 2.7.1 / torch_npu 2.7.1、Python 3.11、CANN 8.3 RC1、ARM64。云镜像：`pytorch_2.7.1-cann_8.3.rc1-py_3.11-hce_2.0.2509-aarch64-snt9b`。

先确认 `/home/ma-user/work` 的 EVS 实际挂载且可写，再在其下恢复 `npu-migration` 和 `smartcourse`。模型、Python 环境、CANN、缓存、临时目录、编译目录和日志均放在该卷。

私有 OBS 中已有原始代码存档、模型和可工作的 CANN 运行档案。对象位置见 `recovery/models.json`。桶名称及访问凭据由使用者通过本机环境提供，公开仓库不保存访问凭据。

使用 `scripts/restore-obs.py` 下载 `--group code` 或 `--group qwen`。代码档案中还保留其他 baseline 的源代码，目录清单见 `recovery/catalogs`。该清单代表已恢复的来源，不表示每个 baseline 已完成当前硬件推理。

原始代码档案恢复至 `npu-migration` 后，将 `recovery/npu-overlay` 覆盖至相同目录结构。原始第三方许可证必须保留。最新 NPU 兼容文件也已单独保存在此仓库中。

CosyVoice 和 FlashHead 使用独立依赖目录。CosyVoice 的 transformers 必须为 4.51.3、tokenizers 为 0.21.1；FlashHead 使用 4.57.3 / 0.22.1。详细已用版本见 `recovery/environment-versions.json`。不要将旧合并依赖表直接用于两个模型。

Qwen 主模型使用 NPU，视觉投影模块使用 CPU。`recovery/huawei/start_qwen36_npu.sh` 为已验证的启动参数。CANN 8.3 需要移除未使用的 recurrent gated delta rule 头文件引用，设置 OPP 的数据链接，并预加载对应 ARM64 `liboptiling.so`。保留的源代码修改及构建脚本位于 `recovery/huawei`。

较长课程使用 16,384 个词元的上下文，并约束 PPT 文字段的输出结构。上传课件保留原始图片位置。CosyVoice 兼容文件使用 CPU ISTFT 重建波形，避免较长语音触发 NPU 算子错误，神经网络推理仍使用 NPU。

本地启动器默认使用一个翻译工作进程和一个数字人工作进程，与本次单卡课程运行配置一致。源讲稿和部分图片说明经过人工审阅，验证记录仅说明本次实际处理范围，不代表任意课件都已通过无人干预运行验证。

课程提交后先写入持久化 `data/state.json` 中的 `executionQueue`。`SMARTCOURSE_TASK_WORKERS` 默认 3，最大 5，控制同时执行的课程任务数量。等待中的消息在后端重启后继续处理，正在执行时被中断的任务保留已有结果，按原有重试操作恢复。

主题生成前，在创建课程页导入当前账户的 PPTX 参考课件。知识库存放于 `SMARTCOURSE_DATA_ROOT/rag/<用户编号>/`，查询、导入和状态接口均需要登录。接口只接受当前账户已上传的课件，不接受任意服务器文件路径。账户之间不共用私有知识库。普通账户不能修改全局服务连接地址。

注册页填写姓名、所属单位、账号、密码及确认密码。注册成功后进入本人的工作台，已有账号使用账号与密码登录。重复账号和两次密码不一致会明确提示。登录成功后清除表单密码，退出后撤销当前会话，并清除当前页面的上传预览和所选任务。草稿、私有知识库和课程任务按账户分别保存。当前采用本地账号注册，不发送短信或邮箱验证码。

各任务仍使用独立的 `tasks/<任务编号>/` 保存输入、参考素材、中间文件和产物，课件生成经验按用户保存。S1/S2 共用一个课件与翻译名额，S3/S4 共用一个媒体名额，S5 使用一个合成名额。不同资源组可以重叠执行，例如一份课程翻译时，另一份课程生成数字人，第三份课程合成视频。资源文件锁保存在持久化数据目录的 `resource-locks/`。同一数据目录启动的后端共用这些执行名额。

`SMARTCOURSE_MEDIA_OVERLAP=1` 可将语音与数字人拆为两个资源组，每组最多执行一个任务，允许 S3 和 S4 重叠。默认值为 0。启用前需检查当前权重、上下文、分辨率和帧数下的合计设备内存占用，不能把一张卡的结果直接用于其他容量或模型配置。课堂回答与课程生成使用相同的语音、数字人资源名额。

可编辑课件的字体嵌入使用 `SMARTCOURSE_EMBED_FONT_REGULAR`、`SMARTCOURSE_EMBED_FONT_BOLD`，字体许可路径使用 `SMARTCOURSE_FONT_LICENSE`。这些文件与 `SMARTCOURSE_CJK_FONT` 均应指向已恢复的持久化字体文件。`SMARTCOURSE_TTS_SPEED=1.0` 使用原始语音速度。

共享实例交给其他任务后，可设置 `SMARTCOURSE_MEDIA_SERVICE_ENABLED=0` 暂停本项目的模型调用。该设置不会改变云实例状态，已生成课程仍可播放，S5 本地合成仍可执行。重新启用前先确认共享实例的实际任务占用、设备内存和模型服务状态。

2026-10-24 在单张 910B1 64GB 上完成 3 人和 5 人提交验证。3 人组全部完成，包含调试和阶段恢复；5 人组为 5 份全新单页短课，全部完成共用时 917.4 秒。设备内存采样最高 49,429 / 65,536 MB，未观察到 OOM。额外完成一份两页主题课程，合计 9 份任务、10 页输出。该结果对应本次短课、模型和分辨率，不能直接用于任意长课程。记录及视频保存在工作区持久化目录 `outputs/huawei_rebuild_20261020/smartcourse-concurrency-budget300-20261024/reports/`，教师人工验收尚未进行。

Notebook 每次启动后 SSH 端口可能变化。将最新地址填写至运行目录的 `remote-state.json`，结构见 `config/remote-state.example.json`。只在平台确实显示运行时填写 RUNNING。

建立 SSH 转发，将云端 7812 转发到本机 17813，使用 `.env` 中的本地 Qwen 地址。远端 CosyVoice / FlashHead 路径由 `.env` 配置。应用使用逻辑设备 npu:0，物理卡分配由本次 Notebook 环境决定。

## 费用与数据

停止 Notebook 计算后，保留的 EVS 和 OBS 仍可能计费。2026-10-21 验收结束时 CPU 与 NPU 均已停止。仓库脚本不会自动创建、启动或删除云资源。

GitHub 保存代码和恢复配方，私有 OBS 保存大模型、运行档案和生成产物。重新租用同一镜像后仍需安装或恢复依赖；当前没有在全新空白实例上再次完成整套恢复验收。

恢复下载示例（先 source scripts/persistent-env.sh，安装 requirements/recovery.txt）：

```bash
python scripts/restore-obs.py --group code --destination /path/to/persistent/archives
python scripts/restore-obs.py --group course-models --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group qwen --destination /home/ma-user/work/npu-migration
python scripts/configure-npu.py
```

下载工具只下载文件。解压前使用 tar -tzf 查看目录结构，将原始代码恢复到对应目录，先解压原始档案，再解压较新的运行档案。环境目录未包含在原始代码备份中，需要从匹配镜像复制到 EVS，并安装已记录的依赖。


2026-10-25 在同一单卡配置上新增 8 份多页课程，共 19 页，覆盖中、英、日、韩、德、法。常态 3 人组每份 3 页，全部完成，包含备注写入及术语校验修正后的阶段恢复。高峰 5 人组每份 2 页，全部为新任务和新产物，从执行提交至全部完成共 2033.0 秒，不含注册和素材上传时间。设备内存采样最高 50,611 / 65,536 MB，未观察到 OOM，已记录语言模型、语音和数字人进程重叠。

本次修正了非连续原始页面部件在写入备注时被自动重新编号的问题。AI 与六种标准语言全称视为相同术语，原数字、逻辑运算符和质量阈值保持不变。字幕在保持原文字及时间轴的条件下均衡分行，并避免结尾标点出现在行首。课件文字测量与最终渲染使用同一字体配置，修正德语说明框超出的问题。母版和版式中样式相同的普通段落按完整语句翻译，保留格式节点，字段、公式、超链接和不同格式的段落保持原有处理。

19 页输出均已检查页数、原图、字幕完整性、音视频时长和逐页下载，并逐页查看最终画面。独立 CPU 语音识别只用于辅助核对，不等同于教师听感验收。生成课件中还进行了德语冠词及韩语母版标题的复核修正。所有结果保存在工作区 `outputs/huawei_rebuild_20261020/smartcourse-quality-budget300-20261025/`，教师人工验收尚未进行。

本次租期于 02:11:58 确认停止，旧预算监控已结束。累计两次计算费用按已记录时长估算为 97.44 元，存储另计，仍计入原 300 元总预算。后续共享实例的训练属于另一租期，本任务不得再次停止该实例。当前本地应用暂停模型调用，账号注册、已有课程播放和本地 S5 合成仍可使用。


独立语音识别还发现两处成品音频存在重复或无关短片段。已保留原始PCM和人物视频，在同一任务内删除确认的多余区间，同步更新人物帧、音轨、句子样本时序、课程时间轴与字幕，并重新合成及识别核对。没有借用其他账号的语音或视频，也没有改变原讲稿内容。韩语控制文本已参考 [CosyVoice官方示例](https://github.com/FunAudioLLM/CosyVoice/blob/main/example.py) 改为简短的中文目标语指令。本次成品中的重复句和控制提示已实际处理完成。

2026-10-25 又在三个独立单卡租期生成 16 段未编辑的原始语音。韩语新提示完成两次完整讲稿、三个短句以及后续一次短句对照，独立 CPU 转录未识别出控制提示文字，两次完整讲稿的目标句均只出现一次。日语长句分段中发现后一段以逗号开头，已改为优先使用日语顿号分段，并把后置标点保留在前一段；两次完整讲稿和一个问题句复测未再识别出此前的额外短片段。

连续标准假名读音另生成三段比较，转录差异更多，未采用。最终源码保留片假名读音方式与标点分段修正，和已通过 9 项语音时序、对齐检查的版本一致。日语仍有读音或转录差异，教师听感与教学内容验收待进行，不能将自动识别结果视为所有语言均达到母语教师水平。

三次追加租期的计算费估算分别为 6.15、4.36、4.34 元。本任务累计计算费估算 112.29 元，存储另计，并在原 300 元总预算中另预留 40 元存储及不确定费用。三个租期均已停止并关闭，不能复用旧停止脚本操作其他任务的后续租期。最终复核目录为 `outputs/huawei_rebuild_20261020/smartcourse-ja-reading-budget300-20261025/`，前两段对照分别保存在同级 `smartcourse-speech-check-budget300-20261025/` 和 `smartcourse-speech-phrase-budget300-20261025/`。这些语音复测不增加此前 8 份课程、19 页或 5 人首次执行的统计数量，也不构成最终读音修改后的另一组完整 5 人计时。
