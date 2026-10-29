"""Private per-task Unix-socket worker; keeps only the voice model in memory."""
import argparse
import json
import os
import re
import socket
import tempfile
from pathlib import Path


def configure_session_paths(root):
    root=Path(root).resolve()
    temporary=root/'tmp';cache=root/'cache'
    temporary.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
    os.environ.update(TMPDIR=str(temporary),TEMP=str(temporary),TMP=str(temporary),XDG_CACHE_HOME=str(cache))
    tempfile.tempdir=None


def exchange(socket_path, payload, timeout=900):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout);connection.connect(str(socket_path))
        connection.sendall((json.dumps(payload,ensure_ascii=False)+'\n').encode())
        with connection.makefile('rb') as reader:
            response=json.loads(reader.readline(1024*1024))
        return response


def serve(root):
    from cosyvoice_engine import CosyVoiceEngine
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    socket_path=root/'worker.sock'
    if socket_path.exists():socket_path.unlink()
    model=CosyVoiceEngine()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(socket_path));os.chmod(socket_path,0o600)
        server.listen(1);server.settimeout(600)
        try:
            while True:
                try:connection,_=server.accept()
                except socket.timeout:break
                stop=False
                with connection:
                    try:
                        with connection.makefile('rb') as reader:payload=json.loads(reader.readline(1024*1024))
                        if payload.get('action')=='close':
                            result={'ok':True};stop=True
                        elif payload.get('action')=='ping':result={'ok':True}
                        else:
                            identifier=payload['id']
                            if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('invalid request identifier')
                            output=root/'outputs'/identifier/'output.wav';output.parent.mkdir(parents=True,exist_ok=True)
                            if payload.get('sourceGuide'):
                                if payload['language']!='ja':raise ValueError('guide mode requires Japanese')
                                guide=root/'requests'/(identifier+'.guide.wav')
                                timing=root/'requests'/(identifier+'.guide.timing.json')
                                if str(guide)!=payload['sourceGuide'] or str(timing)!=payload['sourceGuideTiming']:
                                    raise ValueError('invalid guide location')
                                duration=model.convert_voice(guide,timing,root/'reference.wav',output)
                            else:
                                duration=model.synthesize(payload['text'],str(root/'reference.wav'),str(output),payload['language'])
                            result={'ok':True,'duration':duration,'output':str(output)}
                    except Exception as error:
                        result={'ok':False,'error':str(error)}
                    connection.sendall((json.dumps(result,ensure_ascii=False)+'\n').encode())
                if stop:break
        finally:
            socket_path.unlink(missing_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--serve');parser.add_argument('--socket');parser.add_argument('--request');parser.add_argument('--close',action='store_true');parser.add_argument('--ping',action='store_true');args=parser.parse_args()
    if args.serve:
        configure_session_paths(args.serve)
        serve(args.serve)
    else:
        payload={'action':'close' if args.close else 'ping'} if args.close or args.ping else json.loads(Path(args.request).read_text())
        print(json.dumps(exchange(args.socket,payload,20 if args.close or args.ping else 900),ensure_ascii=False),flush=True)
