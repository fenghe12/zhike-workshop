# 高教社智能体配置归档

[English](README.md) | 简体中文

`agent-prompt.zh-CN.md` 保存此前实现的“智课工坊·MOOC课程视频生成助手”提示词。旧数字公网地址已替换为 `{{PUBLIC_BASE_URL}}`。

原 `mooc_job_submit_huawei` 插件接收 `pptUrl`、`scriptUrl`、`targetLanguages`、`voiceId`、`teacherImageUrl`。文件需先取得可下载地址，任务编号、进度和结果地址均应读取实际接口返回值。

本目录为配置归档。推送代码不表示已经重新部署华为云服务或修改高教社平台。后续恢复连接时，需要核对当前公网入口、认证方式、任务归属，以及插件参数与实际后端的匹配情况，不能沿用已失效的旧网关地址。
