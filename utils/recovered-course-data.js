const LANGUAGE_DETAILS = require('./language-details')

const STAGE_DEFINITIONS = [
  {
    key: 's1',
    index: 1,
    code: 'S1',
    title: '课件结构化',
    agent: '课程生成智能体',
    summary: '识别课件或生成大纲，形成统一的页级结构化内容。'
  },
  {
    key: 's2',
    index: 2,
    code: 'S2',
    title: '多语种翻译与校验',
    agent: '翻译校验智能体',
    summary: '翻译 PPT 与讲稿，通过四项回译一致性指标自动校验。'
  },
  {
    key: 's3',
    index: 3,
    code: 'S3',
    title: '语音合成',
    agent: '语音合成智能体',
    summary: '合成目标语言语音，生成句级时间戳并映射至 PPT 页面。'
  },
  {
    key: 's4',
    index: 4,
    code: 'S4',
    title: '数字人生成',
    agent: '数字人生成智能体',
    summary: '自动确定数字人位置和避让区域，按音频分段生成数字人。'
  },
  {
    key: 's5',
    index: 5,
    code: 'S5',
    title: '视频合成',
    agent: '视频合成与字幕模块',
    summary: '按统一时间轴合成课件、数字人、语音及 SRT 字幕。'
  }
]

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function createStages(status, currentStage) {
  return STAGE_DEFINITIONS.map((definition) => {
    let stageStatus = 'waiting'
    let progress = 0
    if (status === 'completed' || definition.index < currentStage) {
      stageStatus = 'completed'
      progress = 100
    } else if (definition.index === currentStage && status === 'processing') {
      stageStatus = 'running'
      progress = 48
    } else if (definition.index === currentStage && status === 'failed') {
      stageStatus = 'failed'
      progress = 64
    }
    return Object.assign({}, definition, {
      status: stageStatus,
      progress,
      duration: definition.index === 1 ? '00:45' : definition.index === 2 ? '20:08' : definition.index === 3 ? '19:42' : definition.index === 4 ? '18:16' : '06:51'
    })
  })
}

function buildOutputs() {
  return {
    s1: {
      inputMode: '已有课件素材',
      sourceFile: 'ch1 人工智能概述-英文.pptx',
      sourceSize: '172.1 MB',
      sourcePageImage: '/assets/images/ppt-page-01.png',
      sourcePageResolution: '2500 × 1406',
      sourcePageSamples: [
        { page: 2, title: '课程章节内容', image: '/assets/images/ppt-page-02.png' },
        { page: 28, title: '应用层与开发层', image: '/assets/images/ppt-page-28.png' }
      ],
      pageCount: 38,
      validPageCount: 38,
      chapterCount: 5,
      extractionItems: [
        { label: '标题与正文', value: '38 页', state: '已识别' },
        { label: '讲稿文本', value: '38 页', state: '已提取' },
        { label: '图表与公式', value: '页级区域', state: '已定位' },
        { label: '页面布局', value: '38 份', state: '已生成' }
      ],
      chapters: [
        { number: '01', title: '人工智能的起源与概述', pages: '3—12', description: 'Origin and Overview of Artificial Intelligence' },
        { number: '02', title: '人工智能的历史与趋势', pages: '13—25', description: 'History and Trend of Artificial Intelligence' },
        { number: '03', title: '人工智能系统技术架构', pages: '26—31', description: 'Technical Architecture of Artificial Intelligence Systems' },
        { number: '04', title: '人工智能的机遇与挑战', pages: '32—36', description: 'Opportunities and Challenges in Artificial Intelligence' },
        { number: '05', title: '扩展讨论', pages: '37—38', description: 'Extended Discussion' }
      ],
      pages: [
        {
          page: 1,
          title: 'Chapter 1 Overview of Artificial Intelligence',
          points: [],
          script: 'Chapter 1 Overview of Artificial Intelligence. Su Tonghua, School of Software, Harbin Institute of Technology.',
          imageDescription: '原始课件封面，包含课程标题、讲者和所属单位',
          layout: '标题与正文'
        },
        {
          page: 2,
          title: "This chapter's content",
          points: ['Origin and Overview of Artificial Intelligence', 'History and Trend of Artificial Intelligence', 'Technical Architecture of Artificial Intelligence Systems', 'Opportunities and Challenges in Artificial Intelligence', 'Extended Discussion'],
          script: "This chapter's content: Origin and Overview of Artificial Intelligence; History and Trend of Artificial Intelligence; Technical Architecture of Artificial Intelligence Systems; Opportunities and Challenges in Artificial Intelligence; Extended Discussion.",
          imageDescription: '原始课件五部分教学内容编号列表',
          layout: '标题与正文'
        },
        {
          page: 3,
          title: '1.1 Origin and Overview of Artificial Intelligence',
          points: [],
          script: '1.1 Origin and Overview of Artificial Intelligence. Su Tonghua, School of Software, Harbin Institute of Technology.',
          imageDescription: '原始课件章节分隔页',
          layout: '标题与正文'
        }
      ],
      files: [
        { name: 's1_course_structure.json', type: '真实课件解析结果', size: '23.8 KB' },
        { name: 'ch1 人工智能概述-英文.pptx', type: '原始 PPT 课件', size: '172.1 MB' }
      ]
    },
    s2: {
      sourceLanguage: '英语',
      languages: LANGUAGE_DETAILS.map((item) => item.name),
      activeLanguage: LANGUAGE_DETAILS[0].name,
      iteration: 1,
      maxIterations: 3,
      metrics: clone(LANGUAGE_DETAILS[0].metrics),
      languageProgress: LANGUAGE_DETAILS.map((item) => ({
        name: item.name,
        code: item.code,
        progress: 100,
        state: item.passed ? '校验通过' : '自动修正'
      })),
      samples: clone(LANGUAGE_DETAILS[0].samples),
      languageDetails: clone(LANGUAGE_DETAILS),
      correctionLog: [
        { phase: '翻译输出', message: '38页PPT文本与38页讲稿已生成目标语言版本' },
        { phase: '回译校验', message: '语义、术语、公式数字专名及上下文四项指标已计算' },
        { phase: '校验结论', message: '当前语种达到设定阈值，校验结果已写入报告' }
      ],
      files: [
        { name: 'languages/zh-CN/', type: '中文课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/en-US/', type: '英语课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/ja-JP/', type: '日语课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/ko-KR/', type: '韩语课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/de-DE/', type: '德语课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/fr-FR/', type: '法语课件、讲稿与校验报告', size: '38 页 · 2 份 JSON' },
        { name: 'languages/language-summary.json', type: '多语种结果索引', size: '6 个语种' }
      ]
    },
    s3: {
      referenceAudio: '声线参考_10s.wav',
      referenceDuration: '00:10',
      targetLanguage: '英语',
      generatedDuration: '28:26',
      previewDuration: '00:14',
      previewSentenceCount: 7,
      audioAsset: '/assets/audio/english-page-001.wav',
      audioSampleFile: 'page_001.wav',
      sentenceCount: 721,
      alignedPageCount: 38,
      modelFlow: ['提取声纹嵌入', '零样本声线克隆', '句子切分', 'wav2vec2 特征', 'CTC 强制对齐', '页级时间轴'],
      waveBars: [28, 52, 38, 68, 46, 76, 58, 32, 64, 84, 44, 70, 54, 78, 40, 62, 48, 72, 34, 60, 80, 50, 68, 42],
      sentences: [
        { index: 1, page: 1, start: '00:00.000', end: '00:02.740', text: 'Let\'s officially enter our study of this' },
        { index: 2, page: 1, start: '00:02.740', end: '00:04.820', text: 'course. In the first chapter, we will' },
        { index: 3, page: 1, start: '00:04.820', end: '00:07.000', text: 'mainly learn an overview of artificial' },
        { index: 4, page: 1, start: '00:07.000', end: '00:08.859', text: 'intelligence. We will introduce it from' }
      ],
      pageTimeline: [
        { page: 1, start: '00:00.000', end: '00:14.682', duration: '14.682 s', sentences: 7 },
        { page: 2, start: '00:14.682', end: '00:18.625', duration: '3.943 s', sentences: 1 },
        { page: 3, start: '00:18.625', end: '00:24.507', duration: '5.882 s', sentences: 2 }
      ],
      files: [
        { name: 'english_cloned_voice.wav', type: '目标语言语音', size: '72 个分段文件' },
        { name: 'sentence_timestamps.json', type: '句级时间戳', size: '721 条' },
        { name: 's3_timeline.json', type: '页级时间轴', size: '38 页' }
      ]
    },
    s4: {
      page: 1,
      sourcePpt: 'ch1 人工智能概述-英文.pptx',
      sourcePageImage: '/assets/images/ppt-page-01.png',
      sourcePageResolution: '2500 × 1406',
      totalSegments: 34,
      generatedSegments: 34,
      identityConsistency: '已保持',
      lipSyncScore: '已同步',
      avatarBox: { x: 2020, y: 890, width: 350, height: 430, opacity: 1 },
      placement: '右下空白区域',
      reason: '原始第1页标题位于中部，讲者信息位于下部中央，右下为空白区域；数字人位于右下并与检测区域保持间距。',
      contentRegions: [
        { label: '课程标题', value: 'x 80—2370 · y 520—700', status: '已避让' },
        { label: '讲者信息', value: 'x 950—1580 · y 930—1280', status: '已避让' },
        { label: '图表与公式', value: '本页未检测', status: '无冲突' },
        { label: '数字人', value: 'x 2020—2370 · y 890—1320', status: '已放置' }
      ],
      featureFlow: [
        { title: '身份保持', detail: '头像图像 → 身份编码器 → 身份特征' },
        { title: '唇形驱动', detail: '目标语言音频 → 音频特征 → 交叉注意力 A' },
        { title: '情绪驱动', detail: '音频情绪 + 语义情绪 → 特征融合 → 交叉注意力 B' },
        { title: '分段生成', detail: 'Diffusion Transformer → 表情、唇形与头部动作' }
      ],
      segments: [
        { id: 'SEG-001', pages: '1—3', fps: '25 fps', resolution: '512 × 512', status: '生成完成' },
        { id: 'SEG-002', pages: '4', fps: '25 fps', resolution: '512 × 512', status: '生成完成' },
        { id: 'SEG-003', pages: '5', fps: '25 fps', resolution: '512 × 512', status: '生成完成' },
        { id: 'SEG-034', pages: '38', fps: '25 fps', resolution: '512 × 512', status: '生成完成' }
      ],
      files: [
        { name: 's4_manifest.json', type: '数字人生成清单', size: '6.8 KB' },
        { name: 's4_avatar_videos/', type: '34 段数字人视频', size: '150 个 MP4 产物' }
      ]
    },
    s5: {
      videoName: 'ch01_final.mp4',
      previewImage: '/assets/images/ppt-page-01.png',
      subtitleAsset: 'assets/data/artificial-intelligence-overview-en.srt',
      resolution: '1920 × 1080',
      frameRate: '25 fps',
      duration: '28:26',
      videoCodec: 'H.264 / libx264',
      audioCodec: 'AAC',
      subtitleCount: 721,
      transition: '0.5 秒页面过渡',
      compositionTracks: [
        { name: 'PPT 页面', detail: '38 页 · 页级时间轴', color: 'green' },
        { name: '数字人视频', detail: '34 段 · 边界框定位', color: 'blue' },
        { name: '目标语言语音', detail: '28:26 · AAC', color: 'amber' },
        { name: 'SRT 字幕', detail: '721 条 · 句级时间戳', color: 'purple' }
      ],
      subtitlePreview: [
        { index: 1, time: '00:00:00,000 → 00:00:02,740', text: "Let's officially enter our study of this" },
        { index: 2, time: '00:00:02,740 → 00:00:04,820', text: 'course. In the first chapter, we will' },
        { index: 3, time: '00:00:04,820 → 00:00:07,000', text: 'mainly learn an overview of artificial' }
      ],
      files: [
        { key: 'video', name: 'ch01_final.mp4', type: '课程视频', size: '211.9 MB' },
        { key: 'subtitle', name: '人工智能概述_EN.srt', type: 'SRT 字幕', size: '721 条' },
        { key: 'timeline', name: 's3_timeline.json', type: '页级时间轴', size: '38 页' },
        { key: 'report', name: 'generation_report.json', type: '生成报告', size: '生成产物清单' }
      ]
    }
  }
}

function buildRecoveredTask(options) {
  const config = Object.assign(
    {
      id: 'task_ai_overview_multilingual',
      name: '人工智能概述多语种课程',
      mode: 'upload',
      modeLabel: '已有课件素材',
      sourceLanguage: '英语',
      targetLanguages: ['中文', '英语', '日语', '韩语', '德语', '法语'],
      status: 'completed',
      currentStage: 5,
      overallProgress: 100,
      createdAt: '2026-08-01T08:30:00.000Z',
      updatedAt: '2026-08-01T09:36:00.000Z',
      isRecoveredArtifact: true,
      dataProvenance: 'recovered-real-artifacts'
    },
    options || {}
  )

  config.inputs = Object.assign(
    {
      ppt: { name: 'ch1 人工智能概述-英文.pptx', size: 180476226 },
      topic: ''
    },
    config.inputs || {}
  )
  config.assets = Object.assign(
    {
      referenceAudio: {
        name: '声线参考_10s.wav',
        size: 323662,
        sizeLabel: '316.1 KB · 00:10',
        path: '/assets/audio/speaker-reference-10s.wav',
        sourceFile: '第2章开场_10s.wav'
      },
      referenceImage: {
        name: 'HDTF参考人像.jpg',
        size: 53747,
        sizeLabel: '52.5 KB · 1024 × 1024',
        path: '/assets/images/hdtf-reference.jpg'
      }
    },
    config.assets || {}
  )
  config.languageSummary = config.targetLanguages.join('、')
  config.stages = createStages(config.status, config.currentStage)
  config.outputs = buildOutputs()
  return config
}

function getInitialTasks() {
  return [
    buildRecoveredTask()
  ]
}

module.exports = {
  STAGE_DEFINITIONS,
  clone,
  buildOutputs,
  buildRecoveredTask,
  getInitialTasks
}
