"""Publish the actual Bridge trial scope and measurements into the existing report."""
from pathlib import Path
import base64, csv, html, io, json
H=Path(__file__).resolve().parent
def read(path,default=None): return json.loads(path.read_text()) if path.exists() else default
def download(path,label):
    return '<a download="'+html.escape(path.name)+'" href="data:application/json;base64,'+base64.b64encode(path.read_bytes()).decode()+'">'+html.escape(label)+'</a>'
rows=[];models=[]
execution=read(H/'outputs/execution.json',[])
for directory in ['alibaba_pai_easyanimatev3_xl_2_inp_512x512','wan_ai_wan2_2_s2v_14b']:
    path=H/'framework/adaptations'/directory
    status=read(path/'.benchmark-status.json',{})
    metrics_files=list(path.glob('benchmark_metrics_*pretrained*.json'))
    metrics=read(metrics_files[-1],{}) if metrics_files else {}
    entry=next((r for r in execution if r['adaptation']==directory),{})
    if status.get('status')=='running' and read(H/'lease.json',{}).get('closed'):
        status=dict(status,effective_status='interrupted_by_deadline')
    record=dict(adaptation=directory,status=status,execution=entry,metrics=metrics)
    models.append(record)
    latency=metrics.get('latency_s');memory=metrics.get('peak_memory_mb',metrics.get('peak_memory_allocated_mb',metrics.get('peak_allocated_mb')))
    rows.append('<tr><td>'+('EasyAnimate V3' if directory.startswith('alibaba') else 'Wan2.2 S2V-14B')+'</td><td>'+html.escape(status.get('effective_status',status.get('status','未执行')))+'</td><td>'+str(metrics.get('num_samples',status.get('num_samples',0)))+'</td><td>'+(f'{latency:.4f} 秒' if latency is not None else '未完成')+'</td><td>'+str(memory if memory is not None else '未完成')+'</td><td>'+str(entry.get('adaptation_gate',{}).get('exit_code','未执行'))+' / '+str(entry.get('benchmark_gate',{}).get('exit_code','未执行'))+'</td></tr>')
lease=read(H/'lease.json',{})
provider=read(H/'outputs/provider-probe.json',{})
native=read(H/'outputs/qwen-native-status.json',{})
preflight=read(H/'outputs/npu-short-temp-preflight.json',{})
all_models_passed=all(x['status'].get('status')=='completed' and x['metrics'].get('num_samples',0)>=50 and all(x['execution'].get(k,{}).get('exit_code')==0 for k in ['adaptation_gate','benchmark_gate']) for x in models)
native_tools=native.get('actual_client_tool_calls',[])
native_worker_called=any(x.get('name')=='Bash' and 'qwen_worker_tool.py' in str(x.get('input')) for x in native_tools)
completed=all_models_passed and native_worker_called
summary=dict(framework_source='https://gitcode.com/SLAI/SLAI-AscendBridge2',source_readme_version='2.5',execution_entry='Native Bridge coding client with self-hosted Qwen' if native else 'Codex-compatible AGENTS workflow',native_client=native,historical_external_client_status='Kimi returned401; replaced with self-hosted Qwen when available',models=models,compute=lease,budget=read(H/'outputs/budget-ledger.json'),final_tempdir_correction=read(H/'outputs/tempdir-correction-verification.json'),actual_NPU_preflight=preflight,full_video_pipeline=False,independent_generated_video_quality_evaluation=False,cuda_reference_comparison=False,fresh_isolated_environment_verified=False,requested_adapter_and_benchmark_trial_completed=completed,all_model_runtime_checks_passed=all_models_passed,workflow_completed=completed,native_multiagent_team_executed=False)
(H/'outputs/trial-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
s='<section class="audit" id="ascendbridge-workflow-20261025"><h2>AscendBridge 实际迁移与评测流程 · 2026-10-25</h2>'
s+='<p>本次使用已下载的 SLAI-AscendBridge2 源码，其 README 标注版本为 2.5，调用未修改的官方适配与评测检查器。</p>'
if native:
    s+='<p>现已将原生编码客户端的模型提供方替换为持久化部署的 Qwen3.6-35B-A3B Q8。真实接口工具调用检查通过；原生客户端实际工具调用 '+str(len(native_tools))+' 次，其中包括执行工作进程 '+str(native.get('worker_execution_records',0))+' 次。客户端退出码 '+str(native.get('exit_code'))+'。本次为单工作进程顺序执行，没有启动多智能体团队。Qwen与视频模型在同一张NPU上顺序使用。</p>'
else:s+='<p>历史原生客户端使用Kimi时返回401；此前通过Codex兼容入口生成了适配与评测代码。本次是否已完成Qwen替换见实际接口及客户端记录。</p>'
s+='<p>验证对象为 EasyAnimate V3 和 Wan2.2 S2V 的完整原始主干，加载真实预训练权重。每个模型使用 50 个不同 HDTF case，原始 RGB 规格为 512×512、16 帧；实测对象为其原生 VAE 缓存 latent 的单个去噪时间步前向。没有删减层数，没有加载 DiTalker 或 CogPortrait 新增部件。此项不包含完整视频采样、解码或生成质量评测。</p>'
s+='<div class="scroll"><table><thead><tr><th>模型</th><th>实际状态</th><th>不同输入数</th><th>平均同步前向耗时</th><th>测量阶段峰值已分配设备内存 / MiB</th><th>适配 / 评测检查退出码</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
s+='<p>退出码 0 表示相应检查器通过。每次前向计时包含条件与输入传输、噪声准备和主干计算，不含样本文件读取、输出统计和模型加载。两次预热不计入 50 次均值；保留一次真实 profiler trace。</p>'
if all_models_passed:
    s+='<p class="notice">两模型均完成50个不同真实输入，适配与评测检查通过。该结论仅覆盖上述完整主干单时间步工作负载，不代表完整视频管线或独立质量评测已完成。</p>'
else:
    s+='<p class="notice">当前尚未满足两模型全部50输入及官方完成检查，不将部分执行记为通过。下表和各模型记录显示实际完成数量与失败位置。</p>'
if preflight.get('npu_matmul_passed'):
    s+='<p>此前CANN进程通信报AF_UNIX path too long。现已在Python启动前使用短持久化TMPDIR，并显式更新tempfile.tempdir；真实NPU上的进程通信与矩阵计算复测均通过，耗时 '+f"{preflight['elapsed_seconds']:.2f}"+' 秒。该旧错误不记为模型算子不支持。</p>'
else:s+='<p>此前CANN进程通信因临时路径过长而失败；本地缓存修正检查通过，NPU复测状态以实际记录为准。</p>'
for model in models:
    path=H/'framework/adaptations'/model['adaptation']
    metrics=model['metrics'];status=model['status']
    title='EasyAnimate V3' if model['adaptation'].startswith('alibaba') else 'Wan2.2 S2V-14B'
    s+='<h3>'+title+'</h3>'
    if metrics:
        s+='<p>硬件与加载记录：'+html.escape(json.dumps(metrics.get('hardware'),ensure_ascii=False))+'；完整模型层数 '+str(metrics.get('model_loading',{}).get('layers'))+'；实际融合注意力调用 '+str(metrics.get('attention_adapter_calls'))+' 次。</p>'
        s+='<p>'+download(next(path.glob('benchmark_metrics_*pretrained*.json')),'下载完整性能与版本记录')+'</p>'
    if status.get('exception'):s+='<details><summary>展开实际异常日志</summary><pre style="white-space:pre-wrap">'+html.escape(status['exception'])+'</pre></details>'
    measured=path/'outputs/measured-samples.jsonl'
    if measured.exists():
        entries=[json.loads(line) for line in measured.read_text().splitlines() if line.strip()]
        s+='<details><summary>展开 '+str(len(entries))+' 条实际样本记录</summary><div class="scroll"><table><thead><tr><th>case</th><th>同步前向 / 秒</th><th>输出形状</th><th>数值有限</th></tr></thead><tbody>'
        for row in entries:s+='<tr><td>'+html.escape(row['sample_id'])+'</td><td>'+f"{row['latency_s']:.6f}"+'</td><td>'+html.escape(str(row['latent_shape']))+'</td><td>'+str(row['finite'])+'</td></tr>'
        s+='</tbody></table></div></details>'
s+='<p>仍未完成：匹配输入与软件条件的 CUDA 数值对照、独立视频质量指标、完整视频管线性能评测，以及新建独立环境后的安装验证。当前复用既有持久化模型环境，真实包版本另行保存；生成锁文件不代表已完成全新环境安装。</p>'
s+='<p>Bridge正式看板状态仍保留为进行中：其独立环境验收脚本会计算文件校验值，按现有AGENTS.md要求未调用该脚本。上表的适配与评测检查为独立的源码和运行产物检查，原检查器未修改。</p>'
for name,label in [('qwen-migration-plan.json','Qwen生成的执行方案'),('qwen-final-review.json','Qwen对实际结果的核对')]:
    path=H/'framework'/name
    if path.exists():s+='<p>'+download(path,label)+'</p>'
for name,label in [('qwen-anthropic-tool-probe.json','Qwen真实工具调用记录'),('qwen-native-status.json','原生客户端实际工具记录'),('npu-short-temp-preflight.json','短临时目录真实NPU复测')]:
    path=H/'outputs'/name
    if path.exists():s+='<p>'+download(path,label)+'</p>'
if lease.get('closed') and not lease.get('superseded_by_later_owner'):
    budget=read(H/'outputs/budget-ledger.json',{})
    total=budget.get('estimated_total_cny',lease.get('prior_estimated_cny',0)+lease.get('estimated_session_cny',0))
    s+='<p>本次计算已停止，停止确认时间 '+html.escape(lease.get('stopped_confirmed_at',''))+'。Bridge各次启动计算合计估算 '+f"{budget.get('this_bridge_trial_estimate_cny',0):.2f}"+' 元，连同前次恢复累计估算 '+f'{total:.2f}'+' 元，上限 '+str(budget.get('authorized_budget_cny',lease.get('total_budget_cny',50)))+' 元。此数值为计算价格估算，最终以平台账单为准；原数据盘与 OBS 保留。</p>'
s+='<p>'+download(H/'outputs/trial-summary.json','下载本次完整汇总')+'</p></section>'
(H/'outputs/bridge-report-section.html').write_text(s)
(H/'AscendBridge实际流程报告.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>AscendBridge实际流程</title><style>body{max-width:1200px;margin:30px auto;font:16px/1.7 system-ui;background:#0e161d;color:#dfe8ee;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #52616f;padding:8px}a{color:#78c4fa}.scroll{overflow:auto}.notice{color:#ffc987}</style><body>'+s+'</body></html>')
print(json.dumps({'models':[(x['adaptation'],x['status'].get('status'),x['metrics'].get('num_samples')) for x in models],'compute_closed':lease.get('closed')}))
