"""Send explicit media inputs to the task's running Huawei notebook over SSH."""
import json
import os
import shlex
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import urlparse


def media_service_status():
    if os.environ.get("SMARTCOURSE_REMOTE_MEDIA") != "1":
        return "LOCAL"
    if os.environ.get("SMARTCOURSE_MEDIA_SERVICE_ENABLED", "1") != "1":
        return "INACTIVE"
    state_path = os.environ.get("SMARTCOURSE_REMOTE_STATE")
    if not state_path:
        return "UNCONFIGURED"
    try:
        state = json.loads(Path(state_path).read_text())
    except (OSError, ValueError, TypeError):
        return "UNAVAILABLE"
    lease = state.get('lease') or {}
    if lease.get('enable') and lease.get('type') == 'TIMING':
        deadline = (lease.get('create_at') or 0) + (lease.get('duration') or 0)
        if deadline and time.time() * 1000 >= deadline:
            return 'LEASE_EXPIRED'
    return str(state.get("status") or "UNAVAILABLE").upper()


def _connection():
    state_path = os.environ.get("SMARTCOURSE_REMOTE_STATE")
    if not state_path:
        raise RuntimeError("未配置媒体计算服务连接")
    state = json.loads(Path(state_path).read_text())
    if media_service_status() != "RUNNING":
        raise RuntimeError("媒体计算资源未启动，当前任务已保留")
    endpoint = next((e for e in state.get("endpoints", []) if e.get("service") == "SSH"), None)
    if not endpoint:
        raise RuntimeError("媒体计算服务没有可用的 SSH 地址")
    address = urlparse(endpoint["uri"])
    identity = os.environ.get("SMARTCOURSE_SSH_KEY", str(Path.home()/".ssh/id_rsa"))
    hosts = os.environ.get("SMARTCOURSE_SSH_KNOWN_HOSTS", str(Path.home()/".ssh/known_hosts"))
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=yes",
               "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
               "-o", 'UserKnownHostsFile="'+hosts+'"', "-i", identity]
    control = os.environ.get("SMARTCOURSE_SSH_CONTROL_PATH")
    if control:
        options.extend(["-o", "ControlMaster=auto", "-o", "ControlPersist=600",
                        "-o", 'ControlPath="'+control+'"'])
    return options, address.port, f"{address.username or 'ma-user'}@{address.hostname}"


def _transfer(audio=None, photo=None, text=None, language=None, output=None, device=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    options, port, host = _connection()
    remote_root = os.environ.get("SMARTCOURSE_REMOTE_ROOT", "/home/ma-user/work/smartcourse")
    identifier = uuid.uuid4().hex
    remote = remote_root + "/mooc-jobs/" + identifier
    ssh = ["ssh", *options, "-p", str(port), host]
    scp = ["scp", *options, "-P", str(port)]
    log_path = output.with_suffix(output.suffix + ".remote.log")
    with tempfile.TemporaryDirectory(prefix="smartcourse-media-") as temporary, log_path.open("w") as log:
        directory = Path(temporary)
        payload = {"text": text, "language": language}
        files = []
        if audio:
            reference = Path(audio)
            if not reference.is_file():
                raise ValueError("参考音频或页面音频不存在")
            payload["audio"] = remote + "/audio" + reference.suffix.lower()
            local_audio = directory / ("audio" + reference.suffix.lower())
            local_audio.write_bytes(reference.read_bytes());files.append(local_audio)
        if photo:
            reference = Path(photo)
            if not reference.is_file():
                raise ValueError("参考照片不存在")
            payload["photo"] = remote + "/photo" + reference.suffix.lower()
            local_photo = directory / ("photo" + reference.suffix.lower())
            local_photo.write_bytes(reference.read_bytes());files.append(local_photo)
        payload_file = directory / "request.json"
        payload_file.write_text(json.dumps(payload, ensure_ascii=False))
        files.append(payload_file)
        subprocess.run([*ssh, shlex.join(["mkdir", "-p", remote])], check=True, stdout=log, stderr=log, timeout=45)
        package = Path(__file__).resolve().parents[1]
        if text is not None:
            engine = package / "agents/cosyvoice_engine.py"
            runner = directory / "run.py"
            runner.write_text("import json\nfrom cosyvoice_engine import CosyVoiceEngine\nfrom pathlib import Path\nr=Path(__file__).parent\np=json.loads((r/'request.json').read_text())\nCosyVoiceEngine().synthesize(p['text'],p['audio'],str(r/'output.wav'),p['language'])\n")
            files += [engine, runner]
            environment = {
                "PYTHONPATH": remote_root+"/envs/cosyvoice3-runtime:"+remote_root+"/envs/xtts-runtime:"+remote_root+"/env",
                "SMARTCOURSE_COSYVOICE_ROOT": os.environ["SMARTCOURSE_REMOTE_COSYVOICE_ROOT"],
                "SMARTCOURSE_COSYVOICE_MODEL": remote_root+"/shared/models/Fun-CosyVoice3-0.5B-2512",
                "SMARTCOURSE_REMOTE_MEDIA": "0",
            }
            invocation = ["env", *[f"{k}={v}" for k,v in environment.items()],
                          os.environ.get("SMARTCOURSE_REMOTE_PYTHON", "/home/ma-user/anaconda3/envs/MindSpore/bin/python"), remote+"/run.py"]
            remote_output = remote + "/output.wav"
        else:
            invocation = ["bash", os.environ.get("SMARTCOURSE_REMOTE_FLASHHEAD", remote_root+"/flashhead_generate.sh"),
                          payload["audio"], remote+"/output.mp4", payload["photo"]]
            if device is not None:
                device=int(device)
                if device<0:raise ValueError('无效计算设备编号')
                invocation=['env','ASCEND_RT_VISIBLE_DEVICES='+str(device),'WORLD_SIZE=1','RANK=0','LOCAL_RANK=0',
                            'MASTER_ADDR=127.0.0.1','MASTER_PORT='+str(29500+device),*invocation]
            remote_output = remote + "/output.mp4"
        subprocess.run([*scp, *map(str,files), host+":"+remote+"/"], check=True, stdout=log, stderr=log, timeout=180)
        script = "source /usr/local/Ascend/ascend-toolkit/set_env.sh && " + shlex.join(invocation)
        subprocess.run([*ssh, "bash -lc "+shlex.quote(script)], check=True, stdout=log, stderr=log, timeout=900)
        temporary_output = output.with_name("."+output.name+".download")
        subprocess.run([*scp, host+":"+remote_output, str(temporary_output)], check=True, stdout=log, stderr=log, timeout=180)
        temporary_output.replace(output)
        if text is not None:
            timing = output.with_suffix('.timing.json')
            temporary_timing = timing.with_suffix('.pending.json')
            subprocess.run([*scp, host+":"+remote+"/output.timing.json", str(temporary_timing)],
                           check=True, stdout=log, stderr=log, timeout=60)
            temporary_timing.replace(timing)
    output.with_suffix(output.suffix+".remote.json").write_text(json.dumps({"remoteJob": identifier, "remoteDirectory": remote, "output": str(output)}, indent=2))


def synthesize(text, reference, output, language):
    try:
        _transfer(audio=reference, text=text, language=language, output=output)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("远端语音处理未完成，请检查媒体服务；任务日志已保存") from exc
    with wave.open(str(output)) as stream:
        return stream.getnframes()/stream.getframerate()


def generate_avatar(audio, photo, output, device=None):
    try:
        _transfer(audio=audio, photo=photo, output=output, device=device)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("远端数字人处理未完成，请检查媒体服务；任务日志已保存") from exc
