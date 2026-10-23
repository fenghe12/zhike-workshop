from pathlib import Path
from datetime import datetime
import argparse,json,re,sys,time
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--audio',required=True)
parser.add_argument('--graph',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
source=Path(args.source)/'data_util/deepspeech_features'
path=source/'deepspeech_features.py';text=path.read_text()
updated=re.sub(r'\bnp\.float\b','np.float64',text)
if updated!=text:path.write_text(updated)
import numpy as np
import tensorflow as tf
tf.compat.v1.disable_eager_execution()
tf.config.threading.set_intra_op_parallelism_threads(4)
tf.config.threading.set_inter_op_parallelism_threads(1)
sys.path.insert(0,str(source))
from deepspeech_features import conv_audios_to_deepspeech
started=time.time()
conv_audios_to_deepspeech([args.audio],[args.output],[None],args.graph)
features=np.load(args.output)
assert features.ndim==3 and features.shape[1:]==(16,29)
assert np.isfinite(features).all() and features.shape[0]>=8000-2
dynamic=bool(np.any(np.abs(np.diff(features[:300],axis=0))>1e-5))
assert dynamic
record={'completed_at':datetime.now().astimezone().isoformat(),'source':'Official AD-NeRF DeepSpeech feature extractor',
 'speech_model':'DeepSpeech 0.1.0 frozen model used by the official extractor',
 'shape':list(features.shape),'dtype':str(features.dtype),'finite':True,'nonconstant_first_300_frames':dynamic,
 'tensorflow_version':tf.__version__,'elapsed_seconds':round(time.time()-started,2),
 'compatibility_change':'Removed NumPy deprecated scalar alias only; official audio windows and interpolation retained.'}
Path(args.output).with_suffix('.metadata.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
