from pathlib import Path
import argparse,shutil
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--module',required=True);a=p.parse_args();repo=Path(a.repo)
shutil.copy2(a.module,repo/'agenthoi_runtime_records.py')
path=repo/'scripts/preprocess/preprocess_agent_refine.py';text=path.read_text()
anchor='def parse_args():'
addition='from agenthoi_runtime_records import install as install_runtime_records\ninstall_runtime_records(InternVLBackend, AgentHOIRefiner)\n\n\n'
if addition not in text:assert anchor in text;text=text.replace(anchor,addition+anchor,1)
compile(text,str(path),'exec');path.write_text(text)
print('Official reasoning-turn recording and progress reporting installed',flush=True)
