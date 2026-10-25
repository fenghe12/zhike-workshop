# Higher Education Press agent configuration archive

English | [简体中文](README.zh-CN.md)

`agent-prompt.zh-CN.md` preserves the previously implemented configuration for **智课工坊·MOOC课程视频生成助手** on the Higher Education Press agent platform. Old numeric public endpoints have been replaced with `{{PUBLIC_BASE_URL}}`.

The historical `mooc_job_submit_huawei` integration accepts `pptUrl`, `scriptUrl`, `targetLanguages`, `voiceId`, and `teacherImageUrl`. Uploads must resolve to downloadable URLs before submission; task identifiers, progress and output URLs must come from the service response.

This is a configuration archive. Uploading it to GitHub does not redeploy the cloud service or change the existing agent. Before reconnecting it, verify the current public endpoint, authentication, task ownership and agreement between the platform plugin contract and the running backend. Historical gateway addresses are not a current deployment configuration.
