"""Generate page-aligned topic narration using the deployed DeepPresenter model."""
import json
import re
import os
from pathlib import Path
import requests


def generate_topic_lecture(pages, *, audience, minutes, output, endpoint='http://127.0.0.1:7811/v1/chat/completions'):
    try:
        from .narration_style import DIRECT_TEACHING_RULE, review_teaching_style, style_warning
    except ImportError:
        from narration_style import DIRECT_TEACHING_RULE, review_teaching_style, style_warning
    if os.environ.get('SMARTCOURSE_REMOTE_MEDIA') == '1':
        from .remote_topic_lecture import generate_remote_lecture
        return generate_remote_lecture(pages, audience=audience, minutes=minutes, output=output)
    output = Path(output)
    request = {'pages': pages, 'audience': audience, 'minutes': minutes}
    character_limit = max(80, round(minutes / max(1, len(pages)) * 300))
    result = []
    if output.is_file():
        cached = json.loads(output.read_text(encoding='utf-8'))
        completed = cached.get('pages', [])
        if (cached.get('request') == request and cached.get('narrationRuleVersion') == 3 and isinstance(completed, list)
                and len(completed) <= len(pages)
                and all(p.get('page_id') == source['page_id'] and isinstance(p.get('script_text'), str)
                        and p['script_text'].strip()
                        and (len(p['script_text'].strip()) <= character_limit or p.get('requiresCondensation') is True)
                        and (review_teaching_style(p['script_text'])['passed'] or p.get('narration_style_review',{}).get('continuedAfterRetries'))
                        for p, source in zip(completed, pages))):
            result = completed
    output.parent.mkdir(parents=True, exist_ok=True)
    for page in pages[len(result):]:
        messages = [{'role': 'user', 'content':
                '请为以下课程页面编写中文口头讲稿。只返回讲稿正文，不输出代码、JSON、舞台指令或制作说明。'
                '解释页面中的概念、变量、公式和例子，保持数学条件与事实准确，不增加无来源的事实。'
                '直接向学生讲授知识，不使用“幻灯片介绍了”“本页展示了”等描述页面的句式。'
                f'正文最多 {character_limit} 个字符。精简开场与重复解释，保留定义、条件和计算过程。'
                f'教学对象：{audience}。本页建议时长：{minutes / max(1, len(pages)):.1f}分钟。\n'
                + DIRECT_TEACHING_RULE+'\n'+json.dumps(page, ensure_ascii=False)}]
        for attempt in range(4):
            response = requests.post(endpoint, json={'model': 'DeepPresenter-9B', 'temperature': 0,
                                     'max_tokens': 2000, 'messages': messages}, timeout=300)
            response.raise_for_status()
            text = response.json()['choices'][0]['message']['content']
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
            style = review_teaching_style(text)
            if len(text) <= character_limit and style['passed']:
                break
            messages.extend([{'role': 'assistant', 'content': text}, {'role': 'user', 'content':
                f'上一份有 {len(text)} 个字符，请在 {character_limit} 字以内完整表达知识要点，不能截断句子。'
                +'直接讲授知识，不要说幻灯片介绍或展示了什么。'}])
        requires_condensation = len(text) > character_limit
        if response.json()['choices'][0].get('finish_reason') == 'length':
            raise ValueError(f"第{page['page_id']}页讲稿生成不完整")
        if not text or '<tool_call>' in text or text.startswith('```'):
            raise ValueError(f"第{page['page_id']}页未返回有效讲稿")
        if not style['passed']:style['continuedAfterRetries'] = True
        item = {'page_id': page['page_id'], 'script_text': text, 'script_source': 'DeepPresenter-9B',
                'requiresCondensation': requires_condensation,'narration_style_review':style}
        if not style['passed']:item['narration_warning'] = style_warning(page['page_id'])
        result.append(item)
        pending = output.with_suffix('.pending.json')
        pending.write_text(json.dumps({'request': request, 'pages': result, 'narrationRuleVersion': 3}, ensure_ascii=False, indent=2), encoding='utf-8')
        pending.replace(output)
    return result
