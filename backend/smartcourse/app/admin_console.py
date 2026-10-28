"""Authenticated operations console with aggregate first-party usage statistics."""
from __future__ import annotations

import copy
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .account_security import AuthSecurityError
from .config import SUPPORTED_LANGUAGES
from .course_profile import DOMAINS, AUDIENCES
from .course_duration import DURATION_OPTIONS, course_versions, duration_analysis, duration_by_language
from .visitor_traffic import traffic_report
from .task_model import utc_now
from .user_feedback import CATEGORIES, _language

TZ = ZoneInfo('Asia/Shanghai')
STATUSES = {'new', 'reviewing', 'planned', 'resolved'}


def is_admin(settings, user):
    if not user:
        return False
    accounts = json.loads(os.environ.get('SMARTCOURSE_ADMIN_ACCOUNTS', '[]'))
    path = settings.data_root/'admin-access.json'
    if path.is_file():
        accounts += json.loads(path.read_text(encoding='utf-8')).get('accounts', [])
    return user.get('phone') in accounts


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (TypeError, ValueError):
        return None


def _day(value):
    value = _timestamp(value)
    return datetime.fromtimestamp(value, TZ).strftime('%Y-%m-%d') if value is not None else None


def parse_filters(query):
    values = {key: entries[0] for key, entries in query.items() if entries and entries[0] != ''}
    for key in ('start', 'end'):
        if values.get(key):
            try:
                date = datetime.strptime(values[key], '%Y-%m-%d').replace(tzinfo=TZ)
            except ValueError as exc:
                raise ValueError('日期须为 YYYY-MM-DD') from exc
            values[key+'Epoch'] = (date + (timedelta(days=1) if key == 'end' else timedelta())).timestamp()
    if values.get('startEpoch', 0) >= values.get('endEpoch', float('inf')):
        raise ValueError('开始日期不得晚于结束日期')
    if values.get('language'):
        values['language'] = _language(values['language'])
    if values.get('durationBucket') and values['durationBucket'] not in DURATION_OPTIONS:
        raise ValueError('课程时长区间无效')
    if values.get('category') and any(value not in CATEGORIES for value in values['category'].split(',')):
        raise ValueError('反馈类型无效')
    if values.get('rating'):
        if values['rating'] not in {'1','2','3','4','5','unrated'}:
            raise ValueError('评分筛选无效')
    for key, default, limit in [('page', 1, 100000), ('pageSize', 30, 100)]:
        try:
            value = int(values.get(key, default))
        except (ValueError, TypeError) as exc:
            raise ValueError('分页参数无效') from exc
        if not 1 <= value <= limit:
            raise ValueError('分页参数超出范围')
        values[key] = value
    return values


def _within(value, filters):
    date = _timestamp(value)
    if filters.get('startEpoch') is not None and (date is None or date < filters['startEpoch']): return False
    if filters.get('endEpoch') is not None and (date is None or date >= filters['endEpoch']): return False
    return True


def _test_user(user):
    return bool(user.get('isTestAccount') or str(user.get('phone', '')).endswith('@example.test'))


def _test_feedback(row, users):
    return bool(row.get('isTest') or _test_user(users.get(row.get('createdBy'), {})) or
                str(row.get('comment','')).startswith(('部署自检：','管理后台自检：')))


def _distribution(counter, labels=None):
    total = sum(counter.values())
    return [{'key': key, 'label': (labels or {}).get(key, key or '未填写'), 'count': count,
             'percent': round(count*100/total, 1) if total else 0}
            for key, count in sorted(counter.items(), key=lambda x:(-x[1], x[0]))]


def _stats(values):
    values = sorted(v for v in values if _number(v) and v >= 0)
    return {'samples':len(values), 'totalSeconds':round(sum(values), 1),
            'averageSeconds':round(statistics.mean(values), 1) if values else None,
            'medianSeconds':round(statistics.median(values), 1) if values else None,
            'p90Seconds':round(values[max(0, math.ceil(len(values)*.9)-1)], 1) if values else None}


def _targets(task):
    return [_language(value) for value in task.get('targetLanguages', [])]


def _profile(task):
    value = task.get('inputs', {}).get('courseProfile') or {}
    return {k:value[k] for k in ('domain','audience','topics') if k in value} if isinstance(value, dict) else {}


def _topic(task):
    return str(task.get('inputs', {}).get('topic') or task.get('name') or '未填写')[:240]


class AdminConsole:
    def __init__(self, app):
        self.app = app

    def authorize(self, handler):
        handler._user_id(required=True)
        user = self.app.store.user_for_token(handler._token())
        if not is_admin(self.app.settings, user):
            raise AuthSecurityError('此页面仅限管理员访问', 403)
        return user

    def context(self, filters):
        snapshot = self.app.store.snapshot()
        users = {u['id']:u for u in snapshot.get('users', {}).values()}
        include = filters.get('includeTests') == '1'
        tasks = []
        for task in snapshot.get('tasks', {}).values():
            if not include and (_test_user(users.get(task.get('createdBy'), {})) or task.get('isTest')): continue
            if task.get('inputs', {}).get('interruptionParent'): continue
            if filters.get('userId') and task.get('createdBy') != filters['userId']: continue
            if filters.get('taskId') and task['id'] != filters['taskId']: continue
            if filters.get('language') and filters['language'] not in _targets(task): continue
            if filters.get('mode') and task.get('mode') != filters['mode']: continue
            if filters.get('domain') and _profile(task).get('domain', '') != filters['domain']: continue
            if filters.get('durationBucket') and not course_versions(task, filters.get('language'), filters['durationBucket']): continue
            if filters.get('q') and filters['q'].casefold() not in json.dumps([task.get('name'), task['id'], _topic(task), _profile(task)], ensure_ascii=False).casefold(): continue
            tasks.append(task)
        return snapshot, users, tasks

    def feedback(self, filters):
        snapshot, users, selected = self.context(filters)
        task_ids = {t['id'] for t in selected}
        rows = []
        for feedback in snapshot.get('userFeedback', {}).values():
            if not _within(feedback.get('createdAt'), filters): continue
            if filters.get('includeTests') != '1' and _test_feedback(feedback, users): continue
            if filters.get('userId') and feedback.get('createdBy') != filters['userId']: continue
            if any(filters.get(k) for k in ('taskId','mode','domain','durationBucket','q')) and feedback.get('taskId') not in task_ids: continue
            if filters.get('language') and feedback.get('language') != filters['language']: continue
            if filters.get('category') and not set(filters['category'].split(',')).intersection(feedback.get('categories', [])): continue
            rating = filters.get('rating')
            if rating == 'unrated' and feedback.get('rating') is not None: continue
            if rating and rating != 'unrated' and feedback.get('rating') != int(rating): continue
            if filters.get('feedbackStatus') and feedback.get('status', 'new') != filters['feedbackStatus']: continue
            user = users.get(feedback.get('createdBy'), {})
            task = snapshot.get('tasks', {}).get(feedback.get('taskId'), {})
            rows.append({**copy.deepcopy(feedback), 'userName':user.get('displayName','已删除账号'),
                         'account':user.get('phone',''), 'taskName':task.get('name') or (feedback.get('taskSnapshot') or {}).get('name','一般反馈'),
                         'isTest':_test_feedback(feedback, users)})
        rows.sort(key=lambda row:row['createdAt'], reverse=True)
        ratings = [r['rating'] for r in rows if r.get('rating') is not None]
        counts = Counter(str(r.get('rating') or 'unrated') for r in rows)
        categories = Counter(x for r in rows for x in r.get('categories', []))
        languages = defaultdict(list)
        for row in rows:
            languages[row.get('language') or 'general'].append(row)
        language_quality = []
        for language, entries in languages.items():
            scores = [row['rating'] for row in entries if row.get('rating') is not None]
            language_quality.append({'language':language,'label':SUPPORTED_LANGUAGES.get(language,'一般反馈'),
                                     'feedbackCount':len(entries),'ratedCount':len(scores),
                                     'averageRating':round(statistics.mean(scores),2) if scores else None,
                                     'lowRatingCount':sum(score<=2 for score in scores)})
        start = (filters['page']-1)*filters['pageSize']
        return {'rows':rows[start:start+filters['pageSize']], 'total':len(rows), 'page':filters['page'],
                'averageRating':round(statistics.mean(ratings),2) if ratings else None,
                'ratedCount':len(ratings), 'lowRatingCount':sum(r<=2 for r in ratings),
                'ratingDistribution':_distribution(counts), 'categoryDistribution':_distribution(categories),
                'languageQuality':sorted(language_quality,key=lambda row:-row['feedbackCount'])}

    def overview(self, filters):
        snapshot, users, selected = self.context(filters)
        tasks = [t for t in selected if _within(t.get('createdAt'), filters)]
        active_users = {t.get('createdBy') for t in tasks if t.get('createdBy')}
        events = [e for e in self.app.usage.rows(filters.get('startEpoch'), filters.get('endEpoch'), filters.get('userId')) if e['user_id']]
        if filters.get('includeTests') != '1': events = [e for e in events if not _test_user(users.get(e['user_id'], {}))]
        specific = any(filters.get(k) for k in ('taskId','language','mode','domain','durationBucket','q'))
        if specific:
            ids={t['id'] for t in tasks}; events=[e for e in events if e.get('task_id') in ids]
        domain, audience, topics = Counter(), Counter(), Counter()
        target, source, modes, statuses, course_names, stage_failures = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
        durations = defaultdict(list); waits = defaultdict(list); stage_statuses = defaultdict(Counter); by_user = defaultdict(list); daily=defaultdict(lambda:{'tasks':0,'completed':0,'users':set()})
        pages = total_seconds = retries = 0
        for task in tasks:
            by_user[task.get('createdBy')].append(task)
            target.update(_targets(task)); source.update([_language(task.get('sourceLanguage','中文'))]); modes.update([task.get('mode','unknown')]); statuses.update([task.get('status','unknown')]);course_names.update([_topic(task)])
            profile=_profile(task);domain.update([profile.get('domain') or 'unknown']);audience.update([profile.get('audience') or 'unknown']);topics.update(profile.get('topics') or [])
            day=_day(task.get('createdAt'))
            if day:
                daily[day]['tasks']+=1;daily[day]['completed']+=int(task.get('status')=='completed');daily[day]['users'].add(task.get('createdBy'))
            count=task.get('outputs',{}).get('s1',{}).get('pageCount');pages+=count if isinstance(count,int) else 0
            total_seconds+=sum(v.get('durationSeconds',0) for v in task.get('outputs',{}).get('s3',{}).get('languages',{}).values() if _number(v.get('durationSeconds')))
            retries+=max(0,task['executionCount']-1) if isinstance(task.get('executionCount'),int) else len(task.get('executionHistory',[]))
            for stage in task.get('stages',[]):
                code=stage.get('code','S'+str(stage.get('index')));stage_statuses[code].update([stage.get('status','unknown')])
                if stage.get('status') in ('completed','failed') and _number(stage.get('elapsedSeconds')):durations[code].append(stage['elapsedSeconds'])
                if _number(stage.get('queueWaitSeconds')): waits[code].append(stage['queueWaitSeconds'])
                if stage.get('status')=='failed':stage_failures.update([code])
        event_counts=Counter(e['kind'] for e in events)
        user_rows=[]
        event_users=defaultdict(list)
        for event in events:event_users[event['user_id']].append(event)
        for user_id, user in users.items():
            if filters.get('includeTests')!='1' and _test_user(user):continue
            if filters.get('userId') and user_id!=filters['userId']:continue
            rows=by_user.get(user_id,[]);userevents=event_users.get(user_id,[])
            if specific and not rows:continue
            langs=Counter(v for row in rows for v in _targets(row));tags=Counter(v for row in rows for v in _profile(row).get('topics',[]));days={_day(row.get('createdAt')) for row in rows}|{datetime.fromtimestamp(e['created'],TZ).strftime('%Y-%m-%d') for e in userevents};days.discard(None)
            user_feedback=[f for f in snapshot.get('userFeedback',{}).values() if f.get('createdBy')==user_id and _within(f.get('createdAt'),filters) and (filters.get('includeTests')=='1' or not _test_feedback(f,users)) and (not specific or f.get('taskId') in {t['id'] for t in rows})]
            ratings=[f['rating'] for f in user_feedback if f.get('rating') is not None]
            latest=max([v for v in (_timestamp(row.get('updatedAt')) for row in rows) if v is not None]+[e['created'] for e in userevents],default=None)
            last=datetime.fromtimestamp(latest,TZ).isoformat() if latest is not None else None
            user_rows.append({'id':user_id,'name':user.get('displayName'),'account':user.get('phone'),'institution':user.get('institution'), 'registeredAt':user.get('createdAt'), 'isTest':_test_user(user),'tasks':len(rows),'completed':sum(t.get('status')=='completed' for t in rows),'failed':sum(t.get('status')=='failed' for t in rows),'activeDays':len(days),'lastActive':last or None,'languages':_distribution(langs,SUPPORTED_LANGUAGES),'topics':_distribution(tags),'courseDuration':duration_analysis([version for row in rows for version in course_versions(row,filters.get('language'),filters.get('durationBucket'))]),'domains':_distribution(Counter(_profile(row).get('domain') or 'unknown' for row in rows),{**DOMAINS,'unknown':'未填写'}),'audiences':_distribution(Counter(_profile(row).get('audience') or 'unknown' for row in rows),{**AUDIENCES,'unknown':'未填写'}),'feedbackCount':len(user_feedback),'averageRating':round(statistics.mean(ratings),2) if ratings else None,'logins':sum(e['kind']=='login' for e in userevents),'plays':sum(e['kind']=='result_play' for e in userevents),'downloads':sum(e['kind']=='result_download' for e in userevents),'stageSeconds':{code:_stats([s['elapsedSeconds'] for t in rows for s in t.get('stages',[]) if s.get('code')==code and s.get('status') in ('completed','failed') and _number(s.get('elapsedSeconds'))]) for code in ('S1','S2','S3','S4','S5')}})
        versions=[version for task in tasks for version in course_versions(task,filters.get('language'),filters.get('durationBucket'))]
        stages=[{'code':code, **_stats(durations[code]),'queueWait':_stats(waits[code]),'completed':stage_statuses[code]['completed'],'failed':stage_statuses[code]['failed'],'running':stage_statuses[code]['running']} for code in ('S1','S2','S3','S4','S5')]
        failures=Counter((t.get('error') or {}).get('message','未记录错误说明') for t in tasks if t.get('status')=='failed')
        event_all=self.app.usage.rows();earliest=min((e['created'] for e in event_all),default=None)
        return {'generatedAt':utc_now(),'summary':{'users':len(user_rows),'activeUsers':len(active_users|set(event_users)),'newUsers':sum(_within(u.get('registeredAt'),filters) for u in user_rows),'tasks':len(tasks),'completed':statuses['completed'],'failed':statuses['failed'],'completionRate':round(statuses['completed']*100/len(tasks),1) if tasks else None,'inputPages':pages,'outputMinutes':round(total_seconds/60,1),'reexecutionCount':retries,'logins':event_counts['login'],'plays':event_counts['result_play'],'downloads':event_counts['result_download'],'exampleSelections':event_counts['example_selected']},'targetLanguages':_distribution(target,SUPPORTED_LANGUAGES),'sourceLanguages':_distribution(source,SUPPORTED_LANGUAGES),'domains':_distribution(domain,{**DOMAINS,'unknown':'未填写'}),'audiences':_distribution(audience,{**AUDIENCES,'unknown':'未填写'}),'courseDuration':duration_analysis(versions),'durationByLanguage':duration_by_language(versions),'topics':_distribution(topics),'courseNames':_distribution(course_names)[:30],'modes':_distribution(modes,{'upload':'已有课件','topic':'主题课程','code':'代码课程'}),'statuses':_distribution(statuses),'stageTimes':stages,'failureMessages':_distribution(failures)[:20],'daily':[{'date':date,**{k:v for k,v in row.items() if k!='users'},'users':len(row['users'])} for date,row in sorted(daily.items())],'users':sorted(user_rows,key=lambda x:-x['tasks']),'eventCounts':dict(event_counts),'trackingSince':datetime.fromtimestamp(earliest,TZ).isoformat() if earliest else None,'notes':['MOOC 时长指生成课程视频的播放长度，与 S1–S5 的生成耗时分别统计。','一门课程的不同语种分别计为课程版本；尚未生成的视频不计入播放时长分布。','优先读取视频元数据；历史记录也可读取已验证的页面时间轴。未记录时长不会作为零秒样本。','时长区间包含下限、不包含上限，60 分钟及以上单独统计。','阶段耗时为当前或最近一次阶段执行的总耗时，包含阶段内资源等待；失败与完成分别计数，未记录值不按零计算。','播放、下载、页面访问与登录次数从本次统计功能启用后开始记录，历史未记录的行为无法补算。','主题标签来自用户填写；课程名称列表用于辅助查看，未自动推断偏好。','课程统计来自当前保留的任务，已删除任务不计入课程总数。','历史重新执行次数按现存执行记录计算，缺失记录无法补算。']}

    def traffic(self, filters):
        _,users,selected=self.context(filters)
        events=self.app.usage.rows(filters.get('startEpoch'),filters.get('endEpoch'),filters.get('userId'))
        if filters.get('includeTests')!='1':events=[e for e in events if not _test_user(users.get(e['user_id'],{})) and e.get('detail',{}).get('page')!='deployment_check']
        report=traffic_report(events,users)
        report['databaseReady']={'ipv4':4 in self.app.ip_locator.searchers,'ipv6':6 in self.app.ip_locator.searchers}
        return report

    def tasks(self, filters):
        _,users,tasks=self.context(filters)
        rows=[]
        for task in tasks:
            if not _within(task.get('createdAt'),filters):continue
            if filters.get('taskStatus') and task.get('status')!=filters['taskStatus']:continue
            user=users.get(task.get('createdBy'),{})
            rows.append({'id':task['id'],'name':task.get('name'),'userName':user.get('displayName','历史账号'),'userId':task.get('createdBy'),'account':user.get('phone'),'status':task.get('status'),'mode':task.get('mode'),'languages':_targets(task),'sourceLanguage':task.get('sourceLanguage'),'createdAt':task.get('createdAt'),'updatedAt':task.get('updatedAt'),'topic':_topic(task),'profile':_profile(task),'courseVersions':course_versions(task,filters.get('language'),filters.get('durationBucket')),'stage':task.get('currentStage'),'pageCount':task.get('outputs',{}).get('s1',{}).get('pageCount'),'error':task.get('error'),'stages':[{k:s.get(k) for k in ('code','status','elapsedSeconds','startedAt','completedAt')} for s in task.get('stages',[])]})
        rows.sort(key=lambda r:r.get('createdAt',''),reverse=True);start=(filters['page']-1)*filters['pageSize']
        return {'rows':rows[start:start+filters['pageSize']],'total':len(rows)}

    def get(self, handler, path, query):
        if path == '/v1/admin/access':
            handler._user_id(required=True);user=self.app.store.user_for_token(handler._token());handler._json(200,{'isAdmin':is_admin(self.app.settings,user)});return True
        if not path.startswith('/v1/admin/'):return False
        self.authorize(handler)
        try:
            filters=parse_filters(query)
            if path=='/v1/admin/overview':value=self.overview(filters)
            elif path=='/v1/admin/feedback':value=self.feedback(filters)
            elif path=='/v1/admin/tasks':value=self.tasks(filters)
            elif path=='/v1/admin/traffic':value=self.traffic(filters)
            elif path=='/v1/admin/options':
                s=self.app.store.snapshot();value={'languages':SUPPORTED_LANGUAGES,'domains':DOMAINS,'audiences':AUDIENCES,'durationBuckets':DURATION_OPTIONS,'users':[{'id':u['id'],'name':u.get('displayName'),'account':u.get('phone'),'isTest':_test_user(u)} for u in s.get('users',{}).values()],'courses':[{'id':t['id'],'name':t['name'],'userId':t.get('createdBy'),'isTest':_test_user(next((u for u in s['users'].values() if u['id']==t.get('createdBy')),{}))} for t in s.get('tasks',{}).values()]}
            else:raise AuthSecurityError('管理接口不存在',404)
            handler._json(200,value)
        except ValueError as exc:raise AuthSecurityError(str(exc),400) from exc
        return True

    def put(self, handler, path, payload):
        if not path.startswith('/v1/admin/'):return False
        user=self.authorize(handler);match=re.fullmatch(r'/v1/admin/feedback/(feedback_[a-f0-9]{32})',path)
        if not match:raise AuthSecurityError('管理接口不存在',404)
        status=payload.get('status');note=payload.get('adminNote','')
        if status not in STATUSES or not isinstance(note,str) or len(note)>4000:raise ValueError('处理状态或备注无效')
        def update(data):
            row=data.get('userFeedback',{}).get(match[1])
            if not row:raise ValueError('反馈不存在')
            history=row.setdefault('adminHistory',[]);history.append({'status':status,'note':note.strip(),'by':user['id'],'at':utc_now()});row.update(status=status,adminNote=note.strip(),adminUpdatedAt=utc_now());return row
        handler._json(200,self.app.store.transact(update));return True
