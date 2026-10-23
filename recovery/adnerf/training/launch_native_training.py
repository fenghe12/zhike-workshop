from pathlib import Path
import argparse,os,runpy,sys
import torch
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--part',choices=['HeadNeRF','TorsoNeRF'],required=True);a,remaining=p.parse_known_args()
if remaining and remaining[0]=='--':remaining=remaining[1:]
folder=Path(a.repo)/'NeRFs'/a.part
sys.path.insert(0,str(folder));os.chdir(a.repo);torch.manual_seed(0)
sys.argv=[str(folder/'run_nerf.py'),*remaining]
runpy.run_path(str(folder/'run_nerf.py'),run_name='__main__')
