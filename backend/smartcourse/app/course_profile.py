"""User-declared course segmentation for internal usage analysis."""
DOMAINS = {'computing':'计算机与人工智能','mathematics':'数学','science':'自然科学','engineering':'工程技术',
           'medicine':'医学与健康','humanities':'人文社科','business':'经济管理','languages':'语言学习','arts':'艺术设计','general':'通识教育','other':'其他'}
AUDIENCES = {'primary':'小学','secondary':'中学','undergraduate':'本科','graduate':'研究生','professional':'职业学习者','general':'公众','other':'其他'}


def normalize_profile(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict): raise ValueError('课程分类格式无效')
    domain, audience = value.get('domain',''), value.get('audience','')
    if not isinstance(domain,str) or (domain and domain not in DOMAINS): raise ValueError('课程领域无效')
    if not isinstance(audience,str) or (audience and audience not in AUDIENCES): raise ValueError('面向人群无效')
    topics = value.get('topics', [])
    if not isinstance(topics,list) or len(topics)>10 or any(not isinstance(v,str) or not 1<=len(v.strip())<=60 for v in topics): raise ValueError('主题标签最多 10 个，每个不超过 60 字')
    return {'domain':domain,'audience':audience,'topics':list(dict.fromkeys(v.strip() for v in topics))}
