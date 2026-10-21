"""Package native PDF course results without advertising nonexistent PPTX files."""
import json
import shutil
from pathlib import Path
from .course_archive import archive_course
from .offline_course import write_offline_course
from .page_video_delivery import export_page_videos


def package_pdf_result(root, code, title, video):
    root=Path(root);directory=root/'delivery'/code
    runtime=root/'runtime'/code
    sources={'course.mp4':Path(video),'course.pdf':root/'s2'/code/'translated.pdf',
             'lecture.txt':root/'s3'/code/'lecture.txt','source-lecture.txt':root/'s1'/'lecture.txt',
             'translated-lecture.txt':root/'s2'/code/'lecture.txt','subtitles.srt':runtime/'s3_output'/'subtitles.srt'}
    for name,path in sources.items():
        if not path.is_file():raise ValueError('缺少 PDF 课程交付文件：'+name)
    timeline=json.loads((runtime/'s3_output'/'timeline.json').read_text())
    directory.mkdir(parents=True,exist_ok=True)
    for name,path in sources.items():
        if path.resolve()!=(directory/name).resolve():shutil.copy2(path,directory/name)
    public_timeline={'pages':[{key:value for key,value in page.items() if key in
                     ('page_id','title','duration','start_time','end_time','start','end','script_text')}
                     for page in timeline['pages']]}
    (directory/'timeline.json').write_text(json.dumps(public_timeline,ensure_ascii=False,indent=2))
    pages=export_page_videos(video,timeline,directory/'pages')
    offline=write_offline_course(directory,title,code,timeline)
    archive=archive_course(directory,root/'delivery'/f'{code}.zip')
    return {'video':str(directory/'course.mp4'),'previewPdf':str(directory/'course.pdf'),
            'coursePdf':str(directory/'course.pdf'),'lectureScript':str(directory/'lecture.txt'),
            'sourceLecture':str(directory/'source-lecture.txt'),'translatedLecture':str(directory/'translated-lecture.txt'),
            'srt':str(directory/'subtitles.srt'),'timeline':str(directory/'timeline.json'),
            'offlinePage':str(offline),'downloadBundle':str(archive),'pageVideos':pages,
            'pageCount':len(pages),'fileSizeMb':round((directory/'course.mp4').stat().st_size/1048576,2)}
