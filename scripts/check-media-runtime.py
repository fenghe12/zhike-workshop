"""Check the dedicated model environment before publishing compute readiness."""
from pathlib import Path
import argparse, importlib, json, sys

parser = argparse.ArgumentParser()
parser.add_argument('--engine', choices=['speech', 'avatar'], required=True)
parser.add_argument('--model-root', required=True)
parser.add_argument('--source-root', required=True)
args = parser.parse_args()
models, source = Path(args.model_root), Path(args.source_root)
expected = '4.51.3' if args.engine == 'speech' else '4.57.3'
import transformers
if transformers.__version__ != expected:
    raise RuntimeError('Incorrect dedicated transformers version: '+transformers.__version__+'; expected '+expected)
if args.engine == 'speech':
    sys.path[:0] = [str(source), str(source/'third_party/Matcha-TTS')]
    importlib.import_module('cosyvoice.cli.cosyvoice')
    paths = ['cosyvoice3.yaml', 'llm.pt', 'flow.pt', 'hift.pt', 'speech_tokenizer_v3.onnx', 'campplus.onnx']
else:
    sys.path[:0] = [str(source), str(source/'models')]
    importlib.import_module('flash_head.generate_video')
    if not (source/'infra/config/cyberverse.yaml').is_file():
        raise RuntimeError('Missing avatar runtime configuration')
    paths = ['Model_Lite/diffusion_pytorch_model.safetensors', 'VAE_LTX/diffusion_pytorch_model.safetensors']
for relative in paths:
    path = models/relative
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError('Missing model file: '+relative)
    with path.open('rb') as stream:
        stream.read(1)
print(json.dumps({'engine': args.engine, 'transformers': transformers.__version__, 'importsPassed': True,
                  'modelFilesReadable': len(paths)}))
