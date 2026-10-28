# 校园部署与管理后台

所有应用数据、依赖、模型、临时目录和日志应位于已确认的持久化挂载中。部署前检查挂载、读写权限和正在执行的课程任务，保留平台主进程及 SSH 服务。

## 管理入口

校园网页的 `/#/admin` 提供统一管理。管理员可查看所有用户的评分和反馈、按课程/语种/评分/多选问题类型筛选、记录处理状态和管理备注，并查看用户使用情况、课程视频时长和 S1–S5 处理耗时。

在服务器维护会话中加载实际应用环境，再为已注册账号设置权限：

```bash
python -B -m app.admin_access --account '已注册登录账号'
```

`--remove` 用于移除该账号的管理权限。管理员名单保存在应用数据目录的 `admin-access.json`，无需重启后端。账号密码、登录会话、用户记录和管理员名单不能放入源码仓库。

部署自检和测试账号默认不计入正式统计。需要查看既往测试课程时，在管理后台勾选“包含测试账号和部署自检”。

## 课程时长与生成耗时

MOOC 课程时长为最终视频的播放长度。每个语种单独计为课程版本，按不足 1 分钟、1–3、3–5、5–10、10–20、20–30、30–60 和 60 分钟及以上统计。区间包含下限、不包含上限。未生成视频不计入时长样本，时长未记录不作为零秒样本。

每个用户及各语种可分别查看版本数、总播放时长、平均时长、中位数和最长时长。S1–S5 的生成耗时与资源等待另行统计。

## 访问 IP 与地域

`POST /v1/visits` 记录登录前及登录后的页面访问，后台的“访问 IP 与地域”页显示页面访问次数、独立 IP、关联登录用户、每日访问和大致地域分布。日期和用户筛选适用于该页，访问分布按页面访问次数统计。

访问 IP 来自服务器实际接收到的连接。校园入口代理覆盖客户端提交的转发地址，后端仅接受本机代理提供的地址；客户端请求体不能指定实际访问 IP 或地域。

地域由服务器离线查询，使用 [ip2region 官方 Python 客户端](https://github.com/lionsoul2014/ip2region/tree/master/binding/python)。安装 `requirements/backend-local.txt`，在应用持久化数据目录的 `geoip/` 中准备官方数据库：

- [IPv4 数据库](https://github.com/lionsoul2014/ip2region/blob/master/data/ip2region_v4.xdb)：`ip2region_v4.xdb`。
- [IPv6 数据库](https://github.com/lionsoul2014/ip2region/blob/master/data/ip2region_v6.xdb)：`ip2region_v6.xdb`。
- 保留相应的 [许可文件](https://github.com/lionsoul2014/ip2region/blob/master/LICENSE.md)和下载来源记录。

可用 `SMARTCOURSE_GEOIP_ROOT` 指定其他持久化数据库目录。访问者 IP 不发送给外部查询服务。校园网、VPN 或共享代理可能仅暴露内网或出口地址，不能根据这些地址推断访问者的实际城市，独立 IP 数也不等于独立人数。历史未记录 IP 的访问不补算为真实地域。

访问记录在应用数据目录的 `usage.sqlite3`，管理员接口为 `GET /v1/admin/traffic`。普通用户不能读取访问 IP 明细。

## 校园入口代理

`frontend_proxy.py` 仅依赖标准库，转发 API、素材和视频访问，并保留用户会话与分段读取。使用已部署前端的持久化目录启动，例如：

```bash
python -B deploy/campus/frontend_proxy.py \
  --root '/持久化项目目录/software/frontend-web' \
  --host 0.0.0.0 --port 8080 \
  --backend-port 18774 --adapter-port 18772
```

数据库、应用数据和登录信息不应进入前端静态目录。升级时先确认没有生成中的课程，保留当前版本与数据备份，再重启应用所属服务。
