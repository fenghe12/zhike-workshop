"""Keep diagnostics, complete loss tables, curves and training results in one offline page."""
import base64,csv,html,json,mimetypes,re,shutil,os
from pathlib import Path
from bs4 import BeautifulSoup
H=Path(__file__).resolve().parent
OLD=H.parent/'ditalker-cogportrait-50hdtf-100steps-allzero-20261025'
FIX=H.parent/'ditalker-gradient-repair-50hdtf-100steps-20261025'
target=H/'算子梯度与质量诊断.html'
original=H/'inputs/diagnosis-before-integration.html'
if not original.exists():shutil.copy2(target,original)
diagnosis=BeautifulSoup(original.read_text(),'html.parser')
history=BeautifulSoup((OLD/'50case100step全零初始化训练与推理.html').read_text(),'html.parser')
diagnostic_section=diagnosis.select_one('#operator-audit-20261025')
historical_section=history.select_one('#allzero100-training-20261025')
assert diagnostic_section is not None and historical_section is not None
heading=diagnostic_section.find(['h1','h2'])
if heading is not None:heading.string='修复前的算子、梯度与质量诊断记录'
for text_node in diagnostic_section.find_all(string=True):
    text=str(text_node)
    if text.startswith('若目标是让DiTalker所有新增深层部件获得有效更新'):
        text_node.replace_with('用户已明确零初始化指新增分支最后输出层为零。此前将全部新增参数置零属于理解错误，本次按正确设定重新训练，历史数据保留用于对照。CogPortrait的代理规划与KTO部分仍需另行实现和验证。')
historical_section['id']='historical-allzero100'
for a in historical_section.select('a[href]'):
    href=a['href']
    if not href.startswith(('data:','http:','https:','#')):
        path=(OLD/href).resolve()
        if path.is_file():
            mime='text/csv' if path.suffix=='.csv' else 'application/json'
            a['href']='data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode();a['download']=path.name
def file_link(path,label):
    mime='text/csv' if path.suffix=='.csv' else 'application/json'
    name=path.name
    if path.name=='loss.csv':
        name=('ditalker-last-output-zero100-loss.csv' if FIX in path.parents else 'ditalker-historical-allzero100-loss.csv') if path.parent.name=='ditalker' else 'cogportrait-pose100-loss.csv'
    return '<a download="'+html.escape(name)+'" href="data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()+'">'+html.escape(label)+'</a>'
def loss_table(path,label):
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames;rows=list(reader)
    assert [int(r['step']) for r in rows]==list(range(1,101))
    headings={'step':'步骤','sample':'case','loss':'总loss','gradient_norm':'梯度范数','forward_loss_seconds':'前向与损失/秒','backward_seconds':'反向/秒','gradient_inspection_and_update_seconds':'检查与更新/秒','zero_gradient_group_count':'零梯度组数','missing_gradient_tensor_count':'未连接张量数'}
    return '<h3>'+html.escape(label)+' · 100条完整loss</h3><p>'+file_link(path,'下载完整CSV')+'</p><details><summary>展开全部100行</summary><div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(headings.get(k,k))+'</th>' for k in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(r[k])+'</td>' for k in columns)+'</tr>' for r in rows)+'</tbody></table></div></details>'
repaired=(FIX/'outputs/ditalker/result.json').exists()
losses='<section class="audit" id="complete-loss-records"><h2>两模型完整100步loss与曲线</h2>'
losses+='<p>DiTalker使用本次“仅残差出口为零”的修复训练记录；CogPortrait保留已完成的姿态分支100步记录。此前错误的全部参数为零实验在历史区域保留。</p>' if repaired else '<p>本节先保留历史100步记录，修复完成后将显示新的DiTalker数据。</p>'
curve=FIX/'outputs/loss-models-100steps.png' if repaired and (FIX/'outputs/loss-models-100steps.png').exists() else OLD/'outputs/loss-100steps.png'
losses+='<img alt="两模型各100步原始loss曲线" src="data:image/png;base64,'+base64.b64encode(curve.read_bytes()).decode()+'">'
for name,label in [('ditalker','DiTalker 修复后' if repaired else 'DiTalker 历史全零实验'),('cogportrait','CogPortrait 姿态分支')]:
    root=FIX if name=='ditalker' and repaired else OLD
    losses+=loss_table(root/'outputs'/name/'loss.csv',label)
if repaired:losses+='<details><summary>保留的错误全零初始化DiTalker实验</summary>'+loss_table(OLD/'outputs/ditalker/loss.csv','DiTalker 历史全参数为零')+'</details>'
losses+='</section>'
repair='<section class="audit" id="gradient-repair"><h2>DiTalker最后输出层零初始化：修复训练</h2><p>此前将全部新增参数置零的理解有误。本次保留内部投影、归一化与门控的正常初始化，仅将新增残差分支最后输出层置零，使用已修正的遮罩输入。重新执行50个HDTF case、100步，逐组记录梯度与参数实际变化。</p>'
repair+='<p>零输出层为28层ACA、SCA、ECA各自的出口投影，以及PoseGuider出口卷积，共85层。比例门控保留非零系数以允许梯度传播；REPA是辅助损失投影，保留正常初始化。</p>'
result_path=FIX/'outputs/ditalker/result.json';status_path=FIX/'outputs/ditalker/status.json'
if result_path.exists():
    r=json.loads(result_path.read_text());repair+='<p class="notice">已完成'+str(r['completed_steps'])+'步。非零梯度模块组：'+str(sum(v>0 for v in r['nonzero_gradient_steps_by_group'].values()))+'/'+str(len(r['parameter_groups']))+'。</p>'
    repair+=loss_table(FIX/'outputs/ditalker/loss.csv','DiTalker 修复后')
    if (FIX/'outputs/loss-repair.png').exists():repair+='<img alt="DiTalker修复前后loss与梯度" src="data:image/png;base64,'+base64.b64encode((FIX/'outputs/loss-repair.png').read_bytes()).decode()+'">'
    report_fragment=FIX/'outputs/repair-report-section.html'
    if report_fragment.exists():repair+=report_fragment.read_text()
elif status_path.exists():
    s=json.loads(status_path.read_text());repair+='<p class="notice">当前状态：'+html.escape(str(s.get('stage','准备中')))+'；已完成'+str(s.get('completed_steps',0))+'/100步。</p>'
elif (FIX/'availability-status.json').exists() and json.loads((FIX/'availability-status.json').read_text()).get('waiting'):
    repair+='<p class="notice">修复脚本已准备，正在等待共享单卡的当前任务结束。本次新训练尚未开始；完成后本节将加入新的100条loss、逐组梯度和预览。</p>'
else:repair+='<p class="notice">修复脚本与单卡验证准备中；完成后本节将加入新的100条loss、逐组梯度和预览。</p>'
repair+='</section>'
header='<header class="audit"><h1>DiTalker / CogPortrait 训练与诊断总览</h1><p>完整loss、曲线、诊断、视频与DiTalker修复记录已整合在本文件，离线可查看。</p><nav><a href="#gradient-repair">DiTalker修复训练</a> · <a href="#complete-loss-records">两模型100步loss与曲线</a> · <a href="#operator-audit-20261025">算子与质量诊断</a> · <a href="#historical-allzero100">历史完整训练报告</a></nav></header>'
if repaired:header=header.replace('</header>','<p>'+file_link(FIX/'outputs/ditalker/loss.csv','DiTalker loss CSV')+' · '+file_link(OLD/'outputs/cogportrait/loss.csv','CogPortrait loss CSV')+'</p></header>')
styles=''.join(t.get_text() for t in diagnosis.find_all('style'))+''.join(t.get_text() for t in history.find_all('style'))+'body{max-width:1340px;margin:20px auto;background:#0e161d;padding:20px}.audit{margin:20px 0}.audit table{white-space:nowrap}.audit nav{line-height:2}.audit video{max-width:100%;width:100%}.audit details{margin:15px 0}.audit h1{font-size:30px}#historical-allzero100{padding:25px;border:1px solid #405260;border-radius:14px;margin-top:24px}#historical-allzero100:before{content:"历史记录：以下保留原全零实验，当前修复结果见本页顶部";display:block;padding:16px;background:#302c25;color:#f8dfad}'
content=header+repair+losses+str(diagnostic_section)+str(historical_section)
page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DiTalker / CogPortrait训练、loss、曲线与诊断</title><style>'+styles+'</style><body>'+content+'</body></html>'
def atomic_text(path,value):
    staging=path.with_name('.'+path.name+'.staged')
    try:
        staging.write_text(value);os.replace(staging,path)
    except Exception:
        if staging.exists():staging.unlink()
        raise
atomic_text(target,page)
canonical=Path('/Users/Apple/CodeBuddy/20260914153601/npu_results_overview.html');text=canonical.read_text()
backup=H/'inputs/canonical-before-unification.html'
if not backup.exists() and not backup.with_suffix(backup.suffix+'.gz').exists():shutil.copy2(canonical,backup)
block='<!-- OPERATOR_AUDIT_20261025_START --><style>'+styles.replace('body{','section.unused-global-body{')+'</style>'+content+'<!-- OPERATOR_AUDIT_20261025_END -->'
text,n=re.subn(r'<!-- OPERATOR_AUDIT_20261025_START -->.*?<!-- OPERATOR_AUDIT_20261025_END -->',lambda m:block,text,count=1,flags=re.S);assert n==1;atomic_text(canonical,text)
(H/'outputs/integration-check.json').write_text(json.dumps(dict(unified_report=str(target),embedded_loss_rows={'ditalker_repaired':100,'cogportrait':100,'ditalker_historical':100} if repaired else {'ditalker_historical':100,'cogportrait':100},curves_embedded=True,original_report_embedded=True,diagnostic_report_embedded=True,external_loss_files_required=False),indent=2)+'\n')
print('Unified page updated: both complete100-row loss tables, curves, diagnostics, original report and repair progress.')
