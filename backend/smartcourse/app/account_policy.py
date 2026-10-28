"""Versioned account agreement and separately acknowledged media processing."""
from .task_model import utc_now

POLICY_VERSION = '2026-10-26'
MEDIA_VERSION = '2026-10-26'


def policy_documents():
    return {'version':POLICY_VERSION, 'mediaVersion':MEDIA_VERSION, 'documents':{
        'terms':{'title':'智课工坊用户协议','sections':[
            {'title':'服务内容','text':'智课工坊根据课程主题或课件、讲稿、人物照片和参考音频制作多语言课程材料。生成服务可用时，提交任务会使用配置的计算资源；算力关闭时仅保存任务与素材。'},
            {'title':'账号使用','text':'请妥善保管账号和密码，填写有权使用的账号资料。不得使用他人身份冒用注册，不得通过自动程序批量注册或尝试他人账号。'},
            {'title':'素材和生成结果','text':'请仅上传本人拥有权利或已取得相应使用授权的课件、讲稿、照片和声音。制作人物或声音前，需要单独确认授权。不得冒充他人、制作误导性内容或侵犯他人权益。请在使用生成结果前检查课程内容、翻译、发音与人物表现。'},
            {'title':'数据与账号隔离','text':'课程任务和上传材料按账号管理。公开示例为平台提供的演示素材；上传材料不会自动加入公开示例。'},
            {'title':'服务维护与联系','text':'本课程项目演示站由哈工大 AISS 组运营和维护，联系邮箱为 fenghe021209@gmail.com。服务可能因维护或算力安排暂时不可用。有关账号、材料删除或授权撤回的请求，请通过该邮箱联系。'}]},
        'privacy':{'title':'智课工坊隐私说明','sections':[
            {'title':'运营与联系','text':'个人信息处理与服务维护方为哈工大 AISS 组。联系邮箱：fenghe021209@gmail.com。您可以通过该邮箱提出账号、素材处理、授权撤回和删除请求。'},
            {'title':'处理哪些资料','text':'注册和登录使用您填写的账号、姓名、单位、密码及登录会话。密码经过专用密码派生算法处理后保存。课程制作还会处理您主动提交的课件、讲稿、人物照片、参考音频、语言设置与生成结果。'},
            {'title':'处理目的与范围','text':'账号资料用于注册登录、账号隔离和任务查询。课程文本用于生成和翻译课程材料；人物照片用于生成讲者画面，参考声音用于生成讲解语音。验证码和操作次数记录用于限制自动注册及反复尝试登录。'},
            {'title':'云端处理与保存','text':'本站部署在项目配置的校园或云端服务器。课程文本会发送到管理员配置的模型服务，照片和声音会发送到配置的媒体计算服务。材料和结果保存在当前账号对应的任务及上传目录，供后续查看与下载。使用这些功能需要相应的数据传输和保存。'},
            {'title':'保存与删除','text':'任务和素材会在项目服务期间保存。当前删除任务操作只移除任务记录，不会自动清理所有生成文件和备份。如需删除资料或撤回素材处理授权，请停止新生成任务，并通过 fenghe021209@gmail.com 联系哈工大 AISS 组处理文件及备份。'},
            {'title':'使用统计与改进','text':'平台记录访问 IP、网络出口的大致地域、登录、页面访问、示例选用、课程播放和下载点击，以及课程语种、分类、视频时长、阶段耗时和用户反馈，用于功能改进。管理员可在权限控制下查看，普通账号只能查看自己的数据。IP 地域采用服务器离线查询；校园网、VPN 或代理地址可能无法反映实际地域。课程时长依据生成视频记录，阶段耗时记录处理时间。'},
            {'title':'您的选择','text':'不同意本说明时，可以不注册或不登录。您可以不上传人物照片和声音；需要制作数字讲者或使用参考声音时，再单独确认相应素材处理。公开示例人像为 AI 生成的虚构人物。'}]},
        'media':{'title':'人物照片与参考声音处理说明','sections':[
            {'title':'用途与必要性','text':'数字讲者功能需要使用人物照片生成讲者画面。参考声音功能需要从音频中提取声音特征并合成讲解语音。上传人物照片和参考音频前，需要确认本人使用或已经取得素材权利人的相应授权。'},
            {'title':'处理方式与影响','text':'照片、音频及生成的画面和声音会在云端计算服务中处理，并随课程任务保存。生成内容可能具有与参考人物或声音相似的特征，请核对用途、内容与授权范围后使用，不得用于冒充他人或误导他人。'},
            {'title':'单独选择','text':'同意用户协议不会自动视为同意处理人物照片和参考声音。您需要在上传前单独确认。未确认时不会接收相应素材。更换素材后需要重新确认。'},
            {'title':'撤回与删除请求','text':'您可停止或取消未完成的生成任务，并通过 fenghe021209@gmail.com 向哈工大 AISS 组提出停止处理、删除素材及相关结果的请求。文件与备份的处理需要管理员执行。'}]}}}


def accepted_policy(user):
    value = (user or {}).get('policyConsent') or {}
    return value.get('version') == POLICY_VERSION and value.get('termsAccepted') is True and value.get('privacyAccepted') is True


def validate_policy_consent(payload):
    if payload.get('policyVersion') != POLICY_VERSION or payload.get('termsAccepted') is not True or payload.get('privacyAccepted') is not True:
        raise ValueError('请阅读并同意当前版本的用户协议和隐私说明。')
    return {'version':POLICY_VERSION, 'termsAccepted':True, 'privacyAccepted':True, 'acceptedAt':utc_now()}


def validate_media_consent(value, user_id):
    if not isinstance(value, dict) or value.get('authorized') is not True or value.get('version') != MEDIA_VERSION:
        raise ValueError('请先单独确认人物照片或参考声音的使用授权与素材处理说明。')
    return {'version':MEDIA_VERSION, 'authorized':True, 'scope':'course_avatar_and_voice',
            'acceptedAt':utc_now(), 'userId':user_id}
