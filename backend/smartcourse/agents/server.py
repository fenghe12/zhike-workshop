"""
智课工坊 (SmartCourse) - FastAPI 统一后端服务
5阶段流水线: S1(PPT) → S2(翻译) → S3(TTS) → S4(数字人) → S5(合成)
启动: /mnt/lpai-dione/ssai/cvg/team/fenghe/conda_envs/bagel/bin/python server.py
"""

import os, sys, json, uuid, logging, shutil, time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Depends, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yaml

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("smartcourse")

# ==================== 配置加载 ====================
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(AGENT_DIR, "config.yaml")

with open(CONFIG_PATH, "r") as f:
    CFG = yaml.safe_load(f)

WORKSPACE  = CFG["paths"]["workspace"]
UPLOAD_DIR = CFG["paths"]["uploads"]
STATIC_DIR = os.path.join(AGENT_DIR, "static")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# ==================== 数据库初始化 ====================
from database import (
    init_db, register, login, logout, verify_token,
    get_user_info, create_task_record, update_task_status,
    list_user_tasks, get_task_record, delete_task_record,
    list_all_users, list_all_tasks,
)
init_db()

# ==================== 本地Agent导入 ====================
sys.path.insert(0, AGENT_DIR)
from s1_course_agent import CourseAgent
from s1_ppt_generator import PPTGenerator
from s2_translate_agent import TranslateAgent
from s2_ppt_translate import translate_presentation
from s4_bbox_agent import BBoxAgent
from s4_avatar_agent import AvatarAgent
from s5_compose_agent import ComposeAgent

# ==================== FastAPI ====================
app = FastAPI(title="智课工坊", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ==================== 认证依赖 ====================
def get_current_user(authorization: str = Header(default="")) -> dict:
    """从Header中提取token并验证用户"""
    token = authorization.replace("Bearer ", "").strip()
    user = verify_token(token)
    if not user:
        raise HTTPException(401, "未登录或登录已过期")
    return user


# ==================== 状态管理 ====================
def _sp(tid): return os.path.join(WORKSPACE, tid, "status.json")

def read_status(tid):
    p = _sp(tid)
    return json.load(open(p)) if os.path.exists(p) else None

def write_status(tid, data):
    os.makedirs(os.path.dirname(_sp(tid)), exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(_sp(tid), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def set_stage(tid, stage, state, **info):
    s = read_status(tid) or {"task_id": tid, "stages": {}}
    s["stages"][stage] = {"state": state, "updated_at": datetime.now().isoformat(), **info}
    write_status(tid, s)


# ==================== 流水线执行 ====================
def run_pipeline(task_id: str, params: dict):
    """5阶段顺序执行流水线"""
    try:
        update_task_status(task_id, "running")
        set_stage(task_id, "pipeline", "running")
        td = os.path.join(WORKSPACE, task_id)
        os.makedirs(td, exist_ok=True)

        mode       = params["mode"]
        lang       = params.get("target_language", CFG["defaults"]["target_language"])
        speaker    = params.get("speaker_prompt")
        ref_img    = params.get("ref_image")
        gpu        = params.get("gpu_id", CFG["defaults"]["gpu_id"])

        if not speaker or not os.path.exists(speaker):
            speaker = os.path.join(UPLOAD_DIR, "default_speaker.wav")
        if not ref_img or not os.path.exists(ref_img):
            ref_img = os.path.join(UPLOAD_DIR, "default_avatar.png")

        # ============ S1 ============
        if mode == "upload":
            set_stage(task_id, "s1", "running", mode="upload")
            s1_dir = os.path.join(td, "s1_output")
            os.makedirs(s1_dir, exist_ok=True)
            dst = os.path.join(s1_dir, "generated.pptx")
            if params.get("pptx_path") and os.path.abspath(params["pptx_path"]) != os.path.abspath(dst):
                shutil.copy2(params["pptx_path"], dst)
            s1_res = CourseAgent(workspace=WORKSPACE).run(
                task_id, dst, params.get("script_path")
            )
            set_stage(task_id, "s1", "done", pages=s1_res["page_count"])
        else:
            set_stage(task_id, "s1", "running", mode="generate")
            s1_res = PPTGenerator(
                workspace_root=WORKSPACE,
                rag_root=os.environ.get("SMARTCOURSE_RAG_ROOT", ""),
                require_rag=True,
            ).run(
                task_id=task_id, course_topic=params["course_topic"],
                total_pages=params.get("total_pages", CFG["defaults"]["total_pages"]),
                target_language=lang,
                target_learners=params.get("target_learners", "高校本科生"),
                duration_minutes=params.get("duration_minutes", 45),
            )
            set_stage(task_id, "s1", "done", pages=s1_res.get("pages", 0))

        s1_json = os.path.join(td, "s1_output", "course_structure.json")
        s1_pptx = os.path.join(td, "s1_output", "generated.pptx")

        # ============ S2 ============
        set_stage(task_id, "s2", "running")
        s2_res = TranslateAgent(workspace_root=WORKSPACE).run(
            task_id=task_id, source_json=s1_json, target_language=lang,
        )
        s2_dir = os.path.join(td, "s2_output")
        translated_pptx = os.path.join(s2_dir, "translated.pptx")
        if os.path.exists(s1_pptx):
            import asyncio
            asyncio.run(translate_presentation(s1_pptx, lang, translated_pptx))
        set_stage(task_id, "s2", "done", pages=len(s2_res.get("pages", [])))
        s2_json = os.path.join(s2_dir, "translated_structure.json")

        # ============ S3 ============
        set_stage(task_id, "s3", "running")
        old_cwd = os.getcwd()
        os.chdir(CFG["paths"]["tts"])
        import importlib.util
        tts_path = os.path.join(AGENT_DIR, "s3_tts_agent.py")
        spec = importlib.util.spec_from_file_location("s3_tts_agent", tts_path)
        tts_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tts_mod)
        s3_res = tts_mod.TTSAgent(workspace_root=WORKSPACE, speaker_prompt=speaker).run(
            task_id=task_id, source_json=s2_json,
        )
        os.chdir(old_cwd)
        set_stage(task_id, "s3", "done", duration=s3_res["total_duration"])
        s3_timeline = os.path.join(td, "s3_output", "timeline.json")
        s3_srt = os.path.join(td, "s3_output", "subtitles.srt")

        # ============ S4 ============
        set_stage(task_id, "s4", "running")
        use_pptx = translated_pptx if os.path.exists(translated_pptx) else s1_pptx
        BBoxAgent(workspace_root=WORKSPACE).run(task_id=task_id, pptx_path=use_pptx)
        s4_res = AvatarAgent(
            workspace_root=WORKSPACE, ref_image=ref_img, gpu_id=gpu,
        ).run(task_id=task_id, timeline_json=s3_timeline)
        set_stage(task_id, "s4", "done", pages=s4_res["success_pages"])

        # ============ S5 ============
        set_stage(task_id, "s5", "running")
        bbox_json = os.path.join(td, "s4_output", "bbox.json")
        s5_res = ComposeAgent(workspace_root=WORKSPACE).run(
            task_id=task_id, pptx_path=use_pptx, timeline_json=s3_timeline,
            avatars_dir=os.path.join(td, "s4_output", "avatars"),
            bbox_json=bbox_json if os.path.exists(bbox_json) else None,
            subtitle_srt=s3_srt if os.path.exists(s3_srt) else None,
        )
        set_stage(task_id, "s5", "done", output=s5_res.get("output_path"))
        set_stage(task_id, "pipeline", "done")
        update_task_status(task_id, "done")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        set_stage(task_id, "pipeline", "error", error=str(e))
        update_task_status(task_id, "error", error_msg=str(e))


# ==================== 认证路由 ====================

@app.post("/auth/register")
async def auth_register(username: str = Form(...), password: str = Form(...)):
    """用户注册"""
    result = register(username, password)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"message": "注册成功", "user_id": result["user_id"]}


@app.post("/auth/login")
async def auth_login(username: str = Form(...), password: str = Form(...)):
    """用户登录"""
    result = login(username, password)
    if "error" in result:
        raise HTTPException(401, result["error"])
    return result


@app.post("/auth/logout")
async def auth_logout(user: dict = Depends(get_current_user)):
    """用户登出"""
    return {"message": "已登出"}


@app.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    info = get_user_info(user["id"])
    if not info:
        raise HTTPException(404, "用户不存在")
    return info


# ==================== 业务路由 ====================

@app.get("/")
def root():
    return {"service": "智课工坊", "version": "1.0"}


@app.get("/config")
def get_config():
    return {
        "target_languages": ["English", "中文", "日本語", "한국어", "Deutsch", "Français"],
        "defaults": CFG["defaults"],
    }


@app.post("/upload")
async def upload_file(user: dict = Depends(get_current_user), file: UploadFile = File(...)):
    """上传文件"""
    dest = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{file.filename}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": dest, "filename": file.filename}


@app.post("/tasks")
async def create_task(
    bg: BackgroundTasks,
    user: dict = Depends(get_current_user),
    mode: str = Form(...),
    pptx: Optional[UploadFile] = File(None),
    script: Optional[UploadFile] = File(None),
    course_topic: Optional[str] = Form(None),
    total_pages: Optional[int] = Form(None),
    target_language: Optional[str] = Form(None),
    speaker: Optional[UploadFile] = File(None),
    ref_image: Optional[UploadFile] = File(None),
    gpu_id: Optional[int] = Form(None),
):
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    task_dir = os.path.join(WORKSPACE, task_id)
    os.makedirs(task_dir, exist_ok=True)

    params = {
        "mode": mode,
        "target_language": target_language or CFG["defaults"]["target_language"],
        "gpu_id": gpu_id if gpu_id is not None else CFG["defaults"]["gpu_id"],
    }

    if pptx:
        p = os.path.join(task_dir, "input.pptx")
        with open(p, "wb") as f: shutil.copyfileobj(pptx.file, f)
        params["pptx_path"] = p
    if script:
        p = os.path.join(task_dir, "script.txt")
        with open(p, "wb") as f: shutil.copyfileobj(script.file, f)
        params["script_path"] = p
    if speaker:
        p = os.path.join(task_dir, "speaker_prompt.wav")
        with open(p, "wb") as f: shutil.copyfileobj(speaker.file, f)
        params["speaker_prompt"] = p
    if ref_image:
        p = os.path.join(task_dir, "ref_image.png")
        with open(p, "wb") as f: shutil.copyfileobj(ref_image.file, f)
        params["ref_image"] = p

    if mode == "generate":
        params["course_topic"] = course_topic or ""
        params["total_pages"] = total_pages or CFG["defaults"]["total_pages"]

    # 写入数据库
    create_task_record(
        task_id, user["id"], mode,
        topic=course_topic or "",
        language=params["target_language"],
        pages=params.get("total_pages", CFG["defaults"]["total_pages"]),
    )

    write_status(task_id, {"task_id": task_id, "user_id": user["id"], "params": params, "stages": {}})
    bg.add_task(run_pipeline, task_id, params)
    return {"task_id": task_id}


@app.get("/tasks")
def list_tasks(user: dict = Depends(get_current_user)):
    """获取当前用户的任务列表"""
    db_tasks = list_user_tasks(user["id"])
    result = []
    for t in db_tasks:
        status = read_status(t["task_id"])
        stages = {}
        if status:
            stages = {k: v["state"] for k, v in status.get("stages", {}).items()}
        result.append({
            "task_id": t["task_id"],
            "mode": t["mode"],
            "topic": t["topic"],
            "language": t["language"],
            "status": t["status"],
            "stages": stages,
            "created_at": t["created_at"],
        })
    return {"tasks": result}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, user: dict = Depends(get_current_user)):
    """获取任务详情"""
    rec = get_task_record(task_id)
    if not rec or rec["user_id"] != user["id"]:
        raise HTTPException(404, "任务不存在")
    s = read_status(task_id)
    if not s:
        raise HTTPException(404, "状态不存在")
    return s


@app.get("/tasks/{task_id}/output/{stage}/{filename}")
def download(task_id: str, stage: str, filename: str, user: dict = Depends(get_current_user)):
    """下载输出文件"""
    rec = get_task_record(task_id)
    if not rec or rec["user_id"] != user["id"]:
        raise HTTPException(404, "任务不存在")
    p = os.path.join(WORKSPACE, task_id, f"{stage}_output", filename)
    if not os.path.exists(p):
        raise HTTPException(404, "文件不存在")
    return FileResponse(p)


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    """删除任务"""
    if not delete_task_record(task_id, user["id"]):
        raise HTTPException(404, "任务不存在")
    return {"message": "已删除"}


# ==================== 管理员路由 ====================

@app.get("/admin/users")
def admin_users(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "无权限")
    return {"users": list_all_users()}


@app.get("/admin/tasks")
def admin_tasks(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "无权限")
    return {"tasks": list_all_tasks()}


# ==================== 静态文件（前端） ====================
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CFG["server"]["host"], port=CFG["server"]["port"])
