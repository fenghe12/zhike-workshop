Page({
  data: {
    agents: [
      {
        code: 'A1',
        stage: 'S1',
        title: '课程生成智能体',
        color: 'green',
        input: '已有 PPT 或课程主题',
        actions: ['课件页面解析', '课程大纲生成', '逐页内容与讲稿生成', '配套 PPT 生成'],
        output: '标题、要点、讲稿、页面布局及 PPT'
      },
      {
        code: 'A2',
        stage: 'S2',
        title: '翻译校验智能体',
        color: 'blue',
        input: '结构化课件与讲稿',
        actions: ['PPT 文本翻译', '讲稿翻译', '中文回译', '术语、公式、数字、专名校验'],
        output: '多语种 PPT、讲稿和校验结果'
      },
      {
        code: 'A3',
        stage: 'S3',
        title: '语音合成智能体',
        color: 'amber',
        input: '目标语言讲稿与参考音频',
        actions: ['讲者声线特征提取', '目标语言语音合成', '句级时间戳', 'PPT 页级时间轴对齐'],
        output: '讲解音频、句级时间戳和页级时间轴'
      },
      {
        code: 'A4',
        stage: 'S4',
        title: '数字人生成智能体',
        color: 'purple',
        input: '参考图片、语音、讲稿和课件布局',
        actions: ['数字人显示位置', '标题正文图表公式避让', '唇形同步', '表情与头部动作'],
        output: '数字人边界框和分段讲解视频'
      }
    ],
    compose: {
      code: 'M5',
      color: 'teal',
      stage: 'S5',
      title: '视频合成与字幕模块',
      inputs: ['课件页面', '数字人视频', '目标语言语音', '句级字幕'],
      outputs: ['完整课程视频', 'SRT 字幕文件']
    }
  }
})
