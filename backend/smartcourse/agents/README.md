# 恢复的原始智能体代码

此目录保存从 `weights/a800-local-0722/smartcourse` 恢复的原始实现，用于保留课程生成、翻译校验、语音合成、数字人布局、数字人生成和视频合成算法。当前对外服务使用相邻的 `app/` 目录；原始代码中的旧网关格式和历史文件系统路径不作为当前服务配置。

当前网关客户端位于 `../app/gateway.py`，使用 Responses 接口和 `azure-gpt-5_2`，凭据从 `SMARTCOURSE_GW_TOKEN` 环境变量读取。

## S1 教学课件生成规则

`s1_courseware_skill.py` 由当前 `app/` 流程调用，用于课程主题生成模式。该模块要求 S1 依次生成：

1. 课程主旨、目标学习者、课时和先修知识；
2. 章节问题、教学任务、页面预算、案例、视觉载体和理解检查；
3. 规范术语表，包括中英文名称、定义、首次出现位置、允许别名和禁用写法；
4. 逐页 RAG 查询、来源知识单元、教师讲稿和 Manim/PPT 视觉计划；
5. 页面文字与整套课件质量报告。

课程主题模式默认要求 `SMARTCOURSE_RAG_ROOT` 指向已经建立索引的课程知识库。生成目录会增加 `course_brief.json` 和 `course_quality_report.json`。

当前 S1 还会生成以下研究型产物：

- `visual_quality_report.json`：渲染页面、边界、密度和对比度检查，并记录 OCR/VLM 外部检查状态；
- `learning_evaluation.json`：逐页理解检查和 TeachQuiz 输入规范；
- `research_coverage.json`：教学叙事、程序化页面、视觉反馈、多维评分、跨页检查、代码可视化、旁白对齐、多模态检索和经验记忆九项状态；
- `courseware-experience-memory.json`：跨任务保存成功页面和失败模式，等待教师验收结果写回。

`../app/s1_quality_system.py` 保存九项研究来源、九类智能体职责、Manim 场景字段、多模态素材请求、页面渲染检查、整套课件检查和学习评价结构。外部 OCR、VLM 奖励模型或教师评价未执行时，报告中使用 `pending` 状态。
