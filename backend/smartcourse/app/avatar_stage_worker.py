"""Run FLOAT generation in a child process and save its result."""

import argparse
import json
from pathlib import Path

from agents.s4_avatar_agent import AvatarAgent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--reference-image", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--float-dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--page-id", type=int, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    agent = AvatarAgent(
        workspace_root=args.workspace,
        float_dir=args.float_dir,
        ref_image=args.reference_image,
        ckpt_path=args.checkpoint,
        gpu_id=args.gpu_id,
    )
    output = agent.run(
        args.task_id, args.timeline, start_page=args.page_id, end_page=args.page_id
    )
    destination = Path(args.result)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if output.get("error") or output.get("success_pages") != output.get("total_pages"):
        raise RuntimeError("FLOAT did not complete every page")


if __name__ == "__main__":
    main()
