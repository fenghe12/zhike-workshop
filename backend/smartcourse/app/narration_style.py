"""Recognize slide-report wording in automatically authored teaching narration."""
import re

STYLE_VERSION = 1
DIRECT_TEACHING_RULE = (
    'Speak as the teacher addressing learners directly. State and explain the subject matter, '
    'rather than reporting what a slide, page, or presentation introduces, presents, shows, or associates. '
    'Avoid phrases such as "the slide introduces", "this page shows", "幻灯片介绍了", or "本页展示了" '
    'and their equivalents in the requested language. Preserve every substantive fact, date, name, '
    'condition, and example. Natural guidance such as "compare the two curves" is allowed. '
    'Explain the educational meaning of visible diagrams without inventing details or discussing slide production. '
    'State a definition or historical fact itself, rather than saying that a slide introduces it. '
)

_PATTERNS = [
    r'(?:幻灯片|课件|这一页|本页|该页)(?:中|里|上)?\s*(?:向我们|为我们|主要|首先|接着|随后|还|也|则|将|把|介绍|展示|呈现|讲述|说明|提到|列出|涵盖|讨论|概述|回顾)',
    r'\b(?:this|the|current|next|previous|following)\s+(?:slide|page|presentation)\s+(?:(?:also|then|first|briefly|mainly)\s+)*(?:introduces?|presents?|shows?|describes?|explains?|covers?|discusses?|mentions?|outlines?|associates?|summari[sz]es?|focus(?:es)?\s+on|is\s+about)\b',
    r'(?:この|本|次の|前の)?(?:スライド|ページ)(?:では|には|で|に|は)[^。！？\n]{0,18}(?:紹介|説明|提示|示し|示さ|示す|取り上げ)',
    r'(?:이|해당|이번|다음|본)\s*(?:슬라이드|페이지)(?:에서는|에서|는|가)[^.!?\n]{0,18}(?:소개|설명|보여|제시)',
    r'\b(?:diese|die|der|nächste)\s+(?:folie|präsentation|seite)\s+(?:stellt|zeigt|beschreibt|erklärt|behandelt|präsentiert)\b',
    r'\b(?:cette|la)\s+(?:diapositive|présentation|page)\s+(?:présente|montre|décrit|explique|aborde)\b',
    r'\b(?:этот|данный|следующий|предыдущий)\s+слайд\s+(?:представляет|показывает|описывает|объясняет|рассматривает)\b',
    r'\b(?:esta|la|esa|siguiente)\s+(?:diapositiva|presentación|página)\s+(?:presenta|muestra|describe|explica|introduce|aborda)\b',
]


def review_teaching_style(text):
    matches = [match.group() for pattern in _PATTERNS for match in re.finditer(pattern, text or '', re.I)]
    return {'version': STYLE_VERSION, 'passed': not matches, 'matches': list(dict.fromkeys(matches))}


def authored_by_user(page):
    return any(page.get(key) in {'user_docx','teacher_patch'} for key in ('original_script_source','script_source'))


def style_warning(page_id, retries=3):
    return f'第 {page_id} 页自动讲稿仍含描述幻灯片的句式，已局部修订 {retries} 次并继续生成，请检查讲稿。'
