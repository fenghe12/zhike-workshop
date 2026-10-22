"""Generate a course with the explicitly configured model backend."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def generate_course(topic: str, destination: Path, *, pages: int, audience: str,
                    minutes: int, language: str, requirements: str = "", source_material=None) -> dict:
    if not topic.strip() or not 1 <= pages <= 30:
        raise ValueError("课程主题不能为空，生成页数须为 1 至 30")
    if os.environ.get('SMARTCOURSE_PPT_GENERATOR', 'deeppresenter') == 'qwen':
        from .config import Settings
        from .gateway import ResponsesGateway
        from .course_agent import CourseStructureAgent
        from .pptx_notes import write_speaker_notes
        from .pptx_fonts import apply_language_font
        settings = Settings.from_env()
        prompt_topic = topic + '\nTeaching requirements:\n' + requirements
        if source_material is not None:
            prompt_topic += '\nUse the supplied source material:\n' + json.dumps(source_material, ensure_ascii=False)
        structure = CourseStructureAgent(ResponsesGateway(settings)).from_topic(
            prompt_topic, destination.parent.name, destination,
            total_pages=pages, language=language, target_learners=audience, duration_minutes=minutes)
        structure['course_topic'] = topic
        write_speaker_notes(destination, structure['pages'])
        codes = {'Simplified Chinese': 'zh-CN', 'Chinese': 'zh-CN', 'English': 'en-US',
                 'Japanese': 'ja-JP', 'Korean': 'ko-KR', 'German': 'de-DE', 'French': 'fr-FR', 'Russian': 'ru-RU'}
        apply_language_font(destination, destination, codes.get(language, 'zh-CN'))
        structure_path = destination.parent / 'generated-course-structure.json'
        structure_path.write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = {'engine': settings.gateway_model, 'generator': 'CourseStructureAgent',
                    'generated_pptx': str(destination), 'course_structure': str(structure_path),
                    'source_language': language, 'pages': pages}
        manifest_path = destination.parent / 'generation-manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return {**manifest, 'manifest': str(manifest_path)}
    if os.environ.get('SMARTCOURSE_REMOTE_MEDIA') == '1':
        from .remote_deeppresenter import generate_remote_course
        options = dict(pages=pages, audience=audience, minutes=minutes, language=language, requirements=requirements)
        if source_material is not None:
            options['source_material'] = source_material
        return generate_remote_course(topic, destination, **options)
    root = Path(os.environ.get("SMARTCOURSE_ROOT", "/home/ma-user/work/smartcourse"))
    runtime = root / "pptagent-demo"
    python = os.environ.get("SMARTCOURSE_MEDIA_PYTHON", "/home/ma-user/anaconda3/envs/MindSpore/bin/python")
    required = [runtime / name for name in (
        "run_branch_pipeline.py", "config.official-huawei9b.yaml",
        "mcp.branch-huawei.json", "render_office.py")]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"DeepPresenter 运行文件不存在：{path.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = destination.parent / "deeppresenter"
    work.mkdir(exist_ok=True)
    mcp_config = json.loads(required[2].read_text(encoding="utf-8"))
    def configure(value):
        if isinstance(value, dict):
            if 'PPTAGENT_REQUIRE_IMAGE' in value:
                value['PPTAGENT_REQUIRE_IMAGE'] = '0'
            for item in value.values():
                configure(item)
        elif isinstance(value, list):
            for item in value:
                configure(item)
    configure(mcp_config)
    task_mcp = work / 'mcp.runtime.json'
    task_mcp.write_text(json.dumps(mcp_config), encoding='utf-8')
    context = work / "context.json"
    context.write_text(json.dumps({
        "question": topic.strip(), "current_title": topic.strip(),
        "answer": f"教学对象：{audience}。课程时长：{minutes}分钟。语言：{language}。{requirements}",
        "retrieved": [], "illustration_path": "",
        "restricted_source": source_material,
    }, ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(root / p) for p in (
        "envs/pptagent-runtime", "code/PPTAgent", "envs/deeppresenter",
        "env", "pynini-env/lib/python3.11/site-packages"))
    env["DEEPPRESENTER_ALLOW_NO_DOCKER"] = "1"
    command = [python, str(required[0]), "--context-json", str(context),
               "--output-dir", str(work), "--config", str(required[1]),
               "--mcp", str(task_mcp), "--renderer", str(required[3]),
               "--python", python, "--font", str(root / "shared/smartcourse-cn-font.ttc"),
               "--pages", str(pages)]
    if (work / "branch-research.md").is_file() and (work / "research-events.json").is_file():
        command.append("--resume")
    with (work / "execution.log").open("ab") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=log, timeout=7200)
    if result.returncode:
        raise RuntimeError("DeepPresenter 生成失败，请查看任务生成日志")
    manifest = json.loads((work / "branch-pipeline.json").read_text(encoding="utf-8"))
    deck = Path(manifest["final_pptx"]).resolve()
    if not deck.is_relative_to(work.resolve()) or not deck.is_file():
        raise RuntimeError("DeepPresenter 未返回有效课程文件")
    from pptx import Presentation
    if len(Presentation(deck).slides) != pages:
        raise RuntimeError("DeepPresenter 生成的课程页数与请求不一致")
    shutil.copy2(deck, destination)
    return {"engine": "DeepPresenter-9B", "manifest": str(work / "branch-pipeline.json"),
            "generated_pptx": str(destination)}
