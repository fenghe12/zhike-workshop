from pathlib import Path
import csv
import json
import re
import statistics

HERE = Path(__file__).resolve().parent


def number(value):
    try:
        return float(str(value).replace(',', '').replace('%', '').strip())
    except (ValueError, TypeError):
        return None


def main():
    layers = json.loads((HERE/'layer-summary.json').read_text())
    steps = json.loads((HERE/'step-timings.json').read_text())
    state = json.loads((HERE/'status.json').read_text())
    block_ms = [x['block_npu_stream_ms'] for x in layers]
    categories = ['self_attn','cross_attn','ffn','rotary_position_encoding','sdpa']
    totals = {key:sum((x.get(key+'_npu_stream_ms') or 0) for x in layers) for key in categories}
    exports = []
    fused = []
    core_kernels = []
    device_operator_groups = {}
    operator_statistics = []
    for path in sorted((HERE/'torch_profile').rglob('*.csv')):
        with path.open(encoding='utf-8-sig', errors='replace', newline='') as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            exports.append({'file':str(path.relative_to(HERE)),'columns':fields})
            for row in reader:
                names = [str(value) for key,value in row.items() if key and any(s in key.lower() for s in ['name','type'])]
                text = ' '.join(names)
                normalized = re.sub(r'[^a-z0-9]', '', text.lower())
                if any(term in normalized for term in ['flashattentionscore','fusedinferattentionscore','promptflashattention']):
                    fused.append({'file':str(path.relative_to(HERE)),'row':row})
                if path.name.startswith('op_summary'):
                    name = row.get('Op Name','')
                    duration = number(row.get('Task Duration(us)')) or 0
                    group = name.split('_',1)[0]
                    item = device_operator_groups.setdefault(group,{'count':0,'duration_us':0})
                    item['count'] += 1
                    item['duration_us'] += duration
                    if name.endswith('_FlashAttentionScore') and 'Transpose' not in name:
                        core_kernels.append({'name':name,'duration_us':duration})
                if 'statistic' in path.name.lower():
                    operator_statistics.append({'file':str(path.relative_to(HERE)),'row':row})
    normal = [x['seconds'] for x in steps if not x['instrumented'] and x['step']>1]
    report = {'configuration':state['configuration'],'device':state.get('device_name'),
              'status':state['stage'],'measurement':state['measurement'],
              'uninstrumented_steps':len(normal),
              'mean_uninstrumented_step_seconds':statistics.mean(normal) if normal else None,
              'layer_event_sample_step':3,'detail_event_sample_step':5,
              'layer_times_include_both_cfg_passes':True,
              'layer_count':len(layers),'layer_sum_npu_stream_ms':sum(block_ms),
              'layer_mean_npu_stream_ms':statistics.mean(block_ms),
              'layer_min_npu_stream_ms':min(block_ms),'layer_max_npu_stream_ms':max(block_ms),
              'inclusive_category_totals_npu_stream_ms':totals,
              'fused_attention_operator_observed':bool(core_kernels),'fused_attention_rows':fused,
              'fused_core_kernel_count':len(core_kernels),
              'fused_core_kernel_total_ms':sum(x['duration_us'] for x in core_kernels)/1000,
              'device_operator_groups':device_operator_groups,
              'profiler_csv_exports':exports,'operator_statistics':operator_statistics,
              'limitations':['Event timings are inclusive stream intervals and may contain host-induced idle time.',
                             'Layer categories overlap; self-attention includes rotary encoding and SDPA.',
                             'Layer events and detail events are sampled from separate warmed denoising steps.',
                             'No per-layer synchronization is inserted. Instrumented steps are excluded from baseline speed.',
                             'One step is sampled per timing category; this is a diagnostic measurement, not a repeated benchmark.']}
    (HERE/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key not in ['fused_attention_rows','operator_statistics','profiler_csv_exports']},ensure_ascii=False,indent=2))
    print('Profiler CSV files:',[x['file'] for x in exports])
    print('Fused attention rows:',fused[:3])


if __name__ == '__main__':
    main()
