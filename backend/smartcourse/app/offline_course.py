"""Create a self-contained player page referencing packaged course files."""
from html import escape
from pathlib import Path


def write_offline_course(directory, title, language, timeline):
    directory = Path(directory)
    rows = []
    for page in timeline['pages']:
        number = int(page['page_id'])
        start = float(page.get('start_time', page.get('start')))
        duration = float(page['duration'])
        rows.append(f'<li><button data-seek="{start}">第 {number} 页 <small>{duration:.1f} 秒</small></button>'
                    f'<a href="pages/page-{number:03d}.mp4" download>下载</a></li>')
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + escape(title) + '''</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f4;color:#233c32;font:16px system-ui,sans-serif}header{background:#174c3b;color:white;padding:24px 5%}header p{margin:0 0 8px}h1{font-size:26px;margin:0}main{max-width:1400px;margin:30px auto;padding:0 24px;display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:24px}video{width:100%;background:#111;border-radius:8px}.downloads{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0}a{color:#176d50}aside{background:white;padding:20px;border-radius:8px}h2{font-size:18px;margin-top:0}ul{list-style:none;padding:0;margin:0}li{display:flex;align-items:center;border-bottom:1px solid #e4ebe6;gap:10px}button{flex:1;text-align:left;border:0;background:transparent;padding:15px 0;cursor:pointer;color:#233c32;font:inherit}small{display:block;color:#6e7f76;font-size:12px;margin-top:4px}.note{color:#65756c;font-size:13px;line-height:1.6}@media(max-width:800px){main{grid-template-columns:1fr}header{padding:22px}}
</style><header><p>智课工坊 · 课程学习</p><h1>''' + escape(title) + '''</h1></header><main><section><video id="course" src="course.mp4" controls preload="metadata"></video>
<p>目标语种：''' + escape(language) + '''</p><nav class="downloads"><a href="course.mp4" download>完整视频</a><a href="course.pptx" download>课程 PPT</a><a href="course.pdf" download>课程 PDF</a><a href="lecture.txt" download>课程讲稿</a><a href="subtitles.srt" download>字幕</a></nav>
<p class="note">解压完整结果包后打开本页。播放和下载无需连接生成服务；课程提问需要在线服务。</p></section><aside><h2>课程目录</h2><ul>''' + ''.join(rows) + '''</ul></aside></main>
<script>const video=document.getElementById('course');document.querySelectorAll('[data-seek]').forEach(button=>button.addEventListener('click',()=>{video.currentTime=Number(button.dataset.seek);video.play().catch(()=>{});}));</script></html>'''
    path = directory / 'index.html'
    if not (directory/'course.pptx').is_file():
        html=html.replace('<a href="course.pptx" download>课程 PPT</a>','')
    path.write_text(html, encoding='utf-8')
    return path
