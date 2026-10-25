"""Render complete real training and preview results into the existing unified local page."""
import os,sys,json,csv,base64,subprocess,statistics,html
from pathlib import Path
H=Path(__file__).resolve().parent;DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ.update(TMPDIR=str(H/'tmp'),TEMP=str(H/'tmp'),TMP=str(H/'tmp'),MPLCONFIGDIR=str(H/'cache/mpl'))
sys.path.insert(0,str(DATA/'python-cpu'))
import numpy as np,cv2,mediapipe as mp
from PIL import Image,ImageDraw,ImageFont
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=H/'outputs';TRAIN=OUT/'ditalker';r=json.loads((TRAIN/'result.json').read_text());rows=[json.loads(x) for x in (TRAIN/'steps.jsonl').read_text().splitlines()]
assert r['completed_steps']==100 and r['all_11_groups_received_nonzero_gradients'] and r['all_11_groups_changed_parameters']
assert len(rows)==100 and len(r['sample_counts'])==50 and set(r['sample_counts'].values())=={2}
metrics=json.loads((OUT/'preview-metrics.json').read_text());assert metrics['completed']
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
references={}
def data(path,mime):return 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
def encode(array,path,identifier):
    audio=DATA/'inputs/features'/(identifier+'.wav');fps=6.25
    p=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',str(array.shape[2])+'x'+str(array.shape[1]),'-r',str(fps),'-i','pipe:0','-i',str(audio),'-t','2.56','-c:v','libx264','-threads','4','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(path)],input=array.tobytes(),capture_output=True,timeout=120);assert p.returncode==0
    probe=json.loads(subprocess.check_output(['/opt/homebrew/bin/ffprobe','-v','error','-count_frames','-show_entries','stream=codec_type,codec_name,width,height,nb_read_frames','-of','json',str(path)]));v=next(s for s in probe['streams'] if s['codec_type']=='video');assert int(v['nb_read_frames'])==16 and v['codec_name']=='h264'
    return probe
cards={}
for variant in ['ditalker-case1-cfg1','ditalker-case1-cfg7','ditalker-case2-cfg1']:
    folder=OUT/'previews'/variant;info=json.loads((folder/'result.json').read_text());identifier=info['source_sample'];a=np.load(folder/'generated.frames.npy')
    if identifier not in references:
        raw=subprocess.run(['/opt/homebrew/bin/ffmpeg','-v','error','-i',str(DATA/'inputs/clips'/(identifier+'.mp4')),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
        references[identifier]=np.frombuffer(raw,np.uint8).reshape(64,512,512,3)[::4].copy()
    combined=np.zeros((16,556,1024,3),np.uint8);combined[:,44:,:512]=references[identifier];combined[:,44:,512:]=a
    for frame in combined:
        image=Image.fromarray(frame);draw=ImageDraw.Draw(image);draw.text((10,10),'HDTF source',font=font,fill='white');draw.text((522,10),'DiTalker100, zero residual exits, CFG'+str(info['cfg']),font=font,fill='white');frame[:]=np.asarray(image)
    video=folder/'comparison-step100.mp4';poster=folder/'comparison-step100.png';encode(combined,video,identifier);Image.fromarray(combined[8]).save(poster);encode(a,folder/'generated-step100.mp4',identifier)
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True,max_num_faces=1,refine_landmarks=True,min_detection_confidence=.5) as detector:
        detected=[bool(detector.process(np.ascontiguousarray(frame)).multi_face_landmarks) for frame in a]
    metrics['variants'][variant].update(face_detected_frames=sum(detected),face_detection_frames=16)
    card='<article><h3>'+html.escape(variant)+'</h3><video controls loop playsinline preload="metadata" src="'+data(video,'video/mp4')+'" poster="'+data(poster,'image/png')+'"></video><p>左侧原片，右侧本次100步权重生成。512×512，16帧，6.25FPS，25步采样，CFG'+str(info['cfg'])+'。训练集case：'+html.escape(identifier)+'。</p></article>'
    cards[variant]=card
(OUT/'preview-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
names=list(r['parameter_groups']);fig,axes=plt.subplots(1,3,figsize=(16,4.5),dpi=150)
axes[0].plot(range(1,101),[x['loss_terms']['noise_mse'] for x in rows],lw=1,label='Pure denoising MSE');axes[0].plot(range(1,101),[x['loss'] for x in rows],lw=1,label='Total objective');axes[0].set(title='100 actual updates',xlabel='Step',ylabel='Loss');axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
axes[1].barh(names,[r['nonzero_gradient_steps_by_group'][n] for n in names]);axes[1].set(title='Nonzero gradient steps by group',xlabel='Steps out of100',xlim=(0,103));axes[1].tick_params(axis='y',labelsize=7)
axes[2].bar(['Before','After100'],[r['fixed_before']['noise_mse'],r['fixed_after']['noise_mse']],color=['#64748b','#2563eb']);axes[2].set(title='50 paired fixed-noise training cases',ylabel='Pure denoising MSE')
fig.tight_layout();fig.savefig(OUT/'loss-repair.png');plt.close(fig)
old_cog=H.parent/'ditalker-cogportrait-50hdtf-100steps-allzero-20261025/outputs/cogportrait/steps.jsonl'
cog_rows=[json.loads(line) for line in old_cog.read_text().splitlines()]
fig,axes=plt.subplots(1,2,figsize=(12,3.7),dpi=150)
axes[0].plot(range(1,101),[x['loss'] for x in rows],label='Total objective',lw=1)
axes[0].plot(range(1,101),[x['loss_terms']['noise_mse'] for x in rows],label='Pure denoising MSE',lw=1)
axes[0].set(title='DiTalker: last residual outputs zero',xlabel='Actual optimizer step',ylabel='Loss');axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
axes[1].plot(range(1,101),[x['loss'] for x in cog_rows],label='Flow matching MSE',lw=1,color='#15803d')
axes[1].set(title='CogPortrait: retained pose-branch run',xlabel='Actual optimizer step',ylabel='Loss');axes[1].legend(fontsize=8);axes[1].grid(alpha=.2)
fig.tight_layout();fig.savefig(OUT/'loss-models-100steps.png');plt.close(fig)
def table(headers,body):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in body)+'</tbody></table></div>'
groups=[[n,r['first_nonzero_gradient_step_by_group'][n],str(r['nonzero_gradient_steps_by_group'][n])+'/100',r['parameter_changes_by_group'][n]['changed_tensor_count'],r['parameter_changes_by_group'][n]['changed_elements'],f"{r['parameter_changes_by_group'][n]['delta_l2']:.6g}"] for n in names]
quality=[]
for variant,values in metrics['variants'].items():quality.append([variant,f"{values['psnr_db']:.3f}",f"{values['ssim_rgb']:.4f}",f"{values['lpips']:.4f}",str(values['face_detected_frames'])+'/16'])
change=r['fixed_pure_mse_relative_change_percent'];performance=statistics.median(x['forward_loss_seconds']+x['backward_seconds']+x['gradient_inspection_and_update_seconds'] for x in rows)
fragment='<h3>修复结果：11/11组均获得非零梯度并实际更新</h3><p>本次使用单张'+html.escape(r['hardware'])+'。初始化检查确认85个残差出口层的权重与偏置为零；内部投影、LayerNorm和非零门控保留正常初始化。50例各读取2次，共100次实际更新；完整检查点及优化器已重新读取核对，原模型冻结。</p>'
fragment+=table(['新增模块组','首个非零梯度步骤','非零梯度步骤','变化张量数','变化元素数','参数变化L2'],groups)
fragment+='<p>全部新增张量中，'+str(r['tensor_gradient_coverage']['nonzero_gradient_tensors'])+'/'+str(r['tensor_gradient_coverage']['total_added_tensors'])+'个张量曾获得非零梯度。逐张量记录保留，组级通过不等同于每个元素在每一步都有非零梯度。参数变化数包含AdamW权重衰减影响。</p>'
fragment+='<p>50例固定噪声、固定时刻的纯去噪MSE：'+f"{r['fixed_before']['noise_mse']:.6f} → {r['fixed_after']['noise_mse']:.6f}"+'，相对变化'+f'{change:+.3f}%'+'。训练单步中位数'+f'{performance:.2f}'+'秒，最高分配设备内存'+f"{max(x['peak_allocated_bytes'] for x in rows)/1024**3:.2f}"+'GiB。这些为训练集诊断，未完成泛化或收敛验收。</p>'
fragment+='<h3>本次100步权重的真实预览</h3>'+cards['ditalker-case1-cfg1']+cards['ditalker-case2-cfg1']+'<details><summary>同一case的CFG7对照</summary>'+cards['ditalker-case1-cfg7']+'</details>'
fragment+=table(['输出','PSNR↑','SSIM↑','LPIPS↓','人脸检出'],quality)+'<p>以上为两个训练集case，所有视频完整内嵌。旧全零实验和旧CogPortrait记录保留在本页后文。</p>'
if (H/'resource-inventory.json').exists():
    resource=json.loads((H/'resource-inventory.json').read_text());fragment+='<p>计算状态查询：'+html.escape(resource['checked_at'])+'，'+('CPU与NPU实例均停止。' if resource['all_compute_stopped'] else '计算状态按当前查询记录显示。')+'</p>'
if (H/'budget-ledger.json').exists():
    ledger=json.loads((H/'budget-ledger.json').read_text())
    if 'estimated_total_compute_cny' in ledger:fragment+='<p id="repair-budget-record">本次预算50元；按使用时段保守估算算力费用'+f"{ledger['estimated_total_compute_cny']:.2f}"+'元，包含结果恢复连接期间。计算已停止。训练与推理产物已完整取回，收集时的SSH中断未改变已保存的模型结果。</p>'
(OUT/'repair-report-section.html').write_text(fragment)
(OUT/'final-summary.json').write_text(json.dumps(dict(all_11_groups_received_nonzero_gradients=True,all_11_groups_changed_parameters=True,loss_rows=100,cases=50,initialization_mode=r['initialization_mode'],fixed_before=r['fixed_before'],fixed_after=r['fixed_after'],fixed_pure_mse_relative_change_percent=change,metrics=metrics),indent=2)+'\n')
print('Rendered real100-step results, all11 group updates and three embedded previews.')
