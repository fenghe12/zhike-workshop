"""Package actual completed task outputs without repeating model inference."""
import json
import shutil
from pathlib import Path


def package_completed_task(task,artifact_root):
    if task.get('status')!='completed':raise ValueError('任务完成后才能整理交付文件')
    artifact_root=Path(artifact_root).resolve();root=artifact_root/'tasks'/task['id']
    def url(path):return '/artifacts/'+str(Path(path).resolve().relative_to(artifact_root))
    outputs={}
    structure_path=root/'s1'/'course_structure.json'
    is_pdf=structure_path.is_file() and json.loads(structure_path.read_text()).get('input_mode')=='existing_pdf'
    for code,existing in task.get('outputs',{}).get('s5',{}).get('languages',{}).items():
        if code not in {'ja-JP','de-DE','en-US','zh-CN','ko-KR','fr-FR','ru-RU'}:raise ValueError('无效语言')
        if is_pdf:
            from .pdf_delivery import package_pdf_result
            packaged=package_pdf_result(root,code,task['name'],root/'runtime'/code/'s5_output'/'final_video.mp4')
            outputs[code]={key:url(value) if isinstance(value,str) else value for key,value in packaged.items()}
            outputs[code]['pageVideos']=[{**page,'path':url(page['path'])} for page in packaged['pageVideos']]
            continue
        portable=root/'portable'/code
        if not (portable/'compatibility.json').is_file():
            from .portable_course import prepare_portable_course
            prepare_portable_course(root/'s3'/code/'course-with-narration.pptx',portable)
        directory=root/'delivery'/code;directory.mkdir(parents=True,exist_ok=True)
        language_root=root/'runtime'/code
        files={'course.mp4':language_root/'s5_output/final_video.mp4','course.pptx':portable/'course-editable.pptx',
               'course-view.pptx':portable/'course-view.pptx','course.pdf':portable/'course.pdf',
               'lecture.txt':root/'s3'/code/'lecture.txt','translated-lecture.txt':root/'s2'/code/'lecture.txt',
               'source-lecture.txt':root/'s1/lecture.txt','subtitles.srt':language_root/'s3_output/subtitles.srt',
               'timeline.json':language_root/'s3_output/timeline.json'}
        for name,source in files.items():
            if not source.is_file():raise ValueError('缺少交付文件：'+name)
            shutil.copy2(source,directory/name)
        shutil.copytree(portable,directory/'preview',dirs_exist_ok=True)
        from .page_video_delivery import export_page_videos
        page_videos=export_page_videos(files['course.mp4'],json.loads(files['timeline.json'].read_text()),directory/'pages')
        portable_report=json.loads((portable/'compatibility.json').read_text(encoding='utf-8'))
        font_note=('已内嵌字体' if portable_report.get('embeddedFamily') else '目标设备需提供简体中文字体')
        (directory/'README.txt').write_text('course.pptx：可编辑课件，'+font_note+'，备注包含对应讲稿。\ncourse-view.pptx：图像页面兼容查看版，正文不可逐字编辑。\ncourse.pdf：内嵌字体的 PDF。\npreview/index.html：不依赖字体的网页预览。\ncourse.mp4：真实课程视频。\nlecture.txt：对应口语讲稿。\nsubtitles.srt：真实合成采样时间戳字幕。\n详细平台测试范围见 preview/validation-matrix.md。\n',encoding='utf-8')
        from .offline_course import write_offline_course
        offline=write_offline_course(directory,task['name'],code,json.loads(files['timeline.json'].read_text()))
        from .course_archive import archive_course
        archive=archive_course(directory, root/'delivery'/f'{code}.zip')
        outputs[code]={**existing,'video':url(directory/'course.mp4'),'coursePptx':url(directory/'course.pptx'),
                       'pageVideos':[{**item,'path':url(item['path'])} for item in page_videos],
                       'offlinePage':url(offline),
                       'viewPptx':url(directory/'course-view.pptx'),'previewPdf':url(directory/'course.pdf'),
                       'portablePreview':url(directory/'preview/index.html'),'lectureScript':url(directory/'lecture.txt'),
                       'translatedLecture':url(directory/'translated-lecture.txt'),'sourceLecture':url(directory/'source-lecture.txt'),
                       'downloadBundle':url(archive),'fileSizeMb':round((directory/'course.mp4').stat().st_size/1048576,2)}
    if not outputs:raise ValueError('任务没有实际视频输出')
    return {'languageCount':len(outputs),'languages':outputs}
