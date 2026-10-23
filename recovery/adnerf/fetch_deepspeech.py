from pathlib import Path
import argparse,ast,requests,zipfile,shutil,json
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--destination',required=True)
args=parser.parse_args()
HERE=Path(args.destination).resolve()
HERE.mkdir(parents=True,exist_ok=True)
source=Path(args.source).resolve()/'data_util/deepspeech_features/deepspeech_store.py'
tree=ast.parse(source.read_text())
function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='get_deepspeech_model_file')
filename=next(ast.literal_eval(x.value) for x in function.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='file_name' for t in x.targets))
url='https://github.com/osmr/deepspeech_features/releases/download/v0.0.1/'+filename+'.zip'
archive=HERE/'deepspeech-0.1.0.zip'
try:
    response=requests.get(url,stream=True,timeout=(25,90));response.raise_for_status()
    expected=int(response.headers.get('Content-Length',0))
    with archive.with_suffix('.zip.part').open('wb') as output:
        for chunk in response.iter_content(4*1024**2):
            if chunk:output.write(chunk)
    part=archive.with_suffix('.zip.part')
    if expected:assert part.stat().st_size==expected
    part.replace(archive)
    with zipfile.ZipFile(archive) as package:
        member=next(x for x in package.namelist() if x.endswith('.pb'))
        with package.open(member) as source,(HERE/'deepspeech-0.1.0.pb').open('wb') as target:shutil.copyfileobj(source,target)
    print(json.dumps({'official_frozen_model':'downloaded','bytes':(HERE/'deepspeech-0.1.0.pb').stat().st_size}),flush=True)
except Exception as error:
    print(json.dumps({'download_failed':type(error).__name__}),flush=True)
    raise SystemExit(1)
