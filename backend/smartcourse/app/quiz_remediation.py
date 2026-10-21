"""Generate a task-scoped explanation video after an incorrect quiz attempt."""
import json
from pathlib import Path

from .interruption_jobs import public_interruption, submit_interruption


def _public(record, question_id):
    value=public_interruption(record)
    value['statusUrl']=f"/v1/questions/{question_id}/remediation/{record['id']}"
    return value


def submit_quiz_remediation(application, question, selected_option_id, learner_id):
    task=application.get_task(question['course_id'])
    if task.get('status')!='completed':
        raise ValueError('课程尚未完成，不能生成错题讲解')
    existing=next((record for record in application.store.snapshot().get('interruptions',{}).values()
                   if record.get('quizQuestionId')==question['question_id']
                   and record.get('learnerId')==learner_id
                   and record.get('selectedOptionId')==selected_option_id),None)
    if existing:return _public(existing,question['question_id'])
    selected=next(item for item in question['options'] if item['id']==selected_option_id)
    correct=next(item for item in question['options'] if item['id']==question['correct_option_id'])
    locale=question['locale']
    page_id=int((question.get('anchor') or {}).get('page_id') or 1)
    media=task['outputs']['s5']['languages'].get(locale)
    if not media:raise ValueError('当前题目语言没有对应课程视频')
    root=Path(application.settings.artifact_root).resolve()
    timeline_path=(root/media['timeline'].removeprefix('/artifacts/')).resolve()
    if root/'tasks'/task['id'] not in timeline_path.parents:
        raise ValueError('课程时间轴来源无效')
    timeline=json.loads(timeline_path.read_text(encoding='utf-8'))
    page=next((item for item in timeline['pages'] if int(item['page_id'])==page_id),None)
    if page is None:raise ValueError('题目关联页面没有时间轴')
    start=float(page.get('start_time',page.get('start')))
    end=float(page.get('end_time',page.get('end')))
    current_time=start+min(.1,max(0,(end-start)/2))
    if locale=='zh-CN':
        question_text=(f"请对这道错题生成专门讲解视频。简明解释错误选项与正确思路，"
                       f"讲解控制在约一百二十字，不要再提问。题目：{question['prompt']}。"
                       f"学生选择：{selected['text']}。正确选项：{correct['text']}。"
                       f"错误选项反馈：{selected.get('feedback','')}。正确选项说明：{correct.get('feedback','')}。")
    else:
        question_text=(f"Create a concise remediation video explanation in {locale}. "
                       f"Explain why the chosen option is wrong and the correct reasoning in about 100 words. "
                       f"Do not ask a follow-up question. Question: {question['prompt']}. "
                       f"Chosen option: {selected['text']}. Correct option: {correct['text']}. "
                       f"Feedback for chosen option: {selected.get('feedback','')}. "
                       f"Correct explanation: {correct.get('feedback','')}.")
    payload={'question':question_text[:4000],'currentPage':page_id,
             'currentTime':current_time,'targetLanguage':locale}
    metadata={'purpose':'quiz_remediation','quizQuestionId':question['question_id'],
              'learnerId':learner_id,'selectedOptionId':selected_option_id,
              'quizPrompt':question['prompt']}
    return _public(submit_interruption(application,task,payload,metadata),question['question_id'])


def get_quiz_remediation(application,question_id,remediation_id,learner_id):
    record=application.store.snapshot().get('interruptions',{}).get(remediation_id)
    if not record or record.get('purpose')!='quiz_remediation' or record.get('quizQuestionId')!=question_id:
        raise KeyError('错题讲解不存在')
    task=application.get_task(record['courseId'])
    if learner_id not in {record.get('learnerId'),task.get('createdBy')}:
        raise PermissionError('无权查看此错题讲解')
    return _public(record,question_id)
