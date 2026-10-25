"""Full-depth frozen backbone benchmark on 50 distinct cached HDTF inputs.

This is a one-timestep latent forward workload at source RGB resolution 512x512,
not video generation or an independent quality/accuracy evaluation. Step 1 saves
a real single-forward profiler trace and synchronized timing metrics. Step 2
saves small output statistics from those SAME measured forwards, without another
50-forward pass. Both original full configuration and real pretrained modes are
supported; config-only results never stand in for pretrained results.
"""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
CACHE_DIR = Path(__file__).resolve().parent / "models"
# Establish persistent caches before torch and third-party imports.
for name, directory in {
    "TMPDIR": HERE / "tmp", "TEMP": HERE / "tmp", "TMP": HERE / "tmp",
    "HF_HOME": CACHE_DIR, "HF_HUB_CACHE": CACHE_DIR,
    "TRANSFORMERS_CACHE": CACHE_DIR, "TORCH_HOME": HERE / "torch-cache",
    "TORCHINDUCTOR_CACHE_DIR": HERE / "compiler-cache",
}.items():
    directory.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(directory)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import torch
import demo
import runtime


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def get_dtype_str(dtype):
    mapping = {torch.float32: "fp32", torch.float16: "fp16", torch.bfloat16: "bf16"}
    if dtype not in mapping:
        raise ValueError(f"Unsupported actual parameter dtype: {dtype}")
    return mapping[dtype]


def load_config_model(device):
    """Original full from_config architecture, explicitly random and untrained."""
    if demo.MODEL_ID.startswith("alibaba-pai/"):
        sys.path.insert(0, str(runtime.OLD / "source/EasyAnimate"))
        from easyanimate.models import Transformer3DModel
        config_path = runtime.OLD / "models/EasyAnimateV3-XL-2-InP-512x512/transformer/config.json"
        model = Transformer3DModel.from_config(json.loads(config_path.read_text()))
        layers = len(model.transformer_blocks)
    else:
        sys.path.insert(0, str(runtime.R / "repos/Wan2.2"))
        from wan.modules.s2v.model_s2v import WanModel_S2V
        config_path = runtime.R / "checkpoints/wan2.2-s2v-14b/config.json"
        model = WanModel_S2V.from_config(json.loads(config_path.read_text()))
        model.to(dtype=torch.bfloat16)
        model.time_embedding.float()
        model.time_projection.float()
        model.head.float()
        demo.install_adapters(device)
        layers = len(model.blocks)
    model.to(device).eval().requires_grad_(False)
    model.bridge_device = device
    model.bridge_loading = {
        "source": "Original complete architecture from_config, random weights",
        "pretrained": False, "layers": layers,
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "config_path": str(config_path), "base_only": True,
    }
    return model


def check_deadline(args):
    if args.deadline_epoch and time.time() >= args.deadline_epoch:
        raise TimeoutError("Authorized benchmark deadline reached before next forward")


def timed_predict(model, sample, args):
    check_deadline(args)
    device = model.bridge_device
    demo.synchronize(device)
    start = time.perf_counter()
    output = demo.predict(model, sample, seed=args.seed, timestep=args.timestep)
    demo.synchronize(device)
    latency = time.perf_counter() - start
    return output, latency


def profiler_context(device, level):
    if str(device).startswith("npu"):
        import torch_npu
        module = torch_npu.profiler
        config = module._ExperimentalConfig(
            profiler_level=getattr(module.ProfilerLevel, {"L0": "Level0", "L1": "Level1", "L2": "Level2"}[level]),
            aic_metrics=module.AiCMetrics.PipeUtilization,
        )
        return module.profile(
            activities=[module.ProfilerActivity.CPU, module.ProfilerActivity.NPU],
            record_shapes=False, profile_memory=False, with_stack=False,
            experimental_config=config,
        )
    return torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CPU],
        record_shapes=False, profile_memory=False, with_stack=False,
    )


def package_versions():
    result = {}
    for name in ("torch", "torch-npu", "diffusers", "transformers", "safetensors", "accelerate", "numpy"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def hardware_info(device):
    result = {"platform": platform.platform(), "machine": platform.machine()}
    if str(device).startswith("npu"):
        result["device_name"] = torch.npu.get_device_name(0)
        props = torch.npu.get_device_properties(0)
        result["device_properties"] = str(props)
        result["total_memory_bytes"] = int(props.total_memory)
    else:
        result["device_name"] = platform.processor() or platform.machine()
    return result


def memory_metrics(device):
    if str(device).startswith("npu"):
        return {
            "peak_memory_mb": torch.npu.max_memory_allocated() / (1024 ** 2),
            "peak_reserved_memory_mb": torch.npu.max_memory_reserved() / (1024 ** 2),
        }
    return {"peak_memory_mb": None, "peak_reserved_memory_mb": None}


def run_demo_dry_run(model, sample, args, load_seconds):
    """Use demo's exact real forward with the already loaded model."""
    output, latency = timed_predict(model, sample, args)
    summary = runtime.tensor_summary(output)
    if not summary["finite"]:
        raise FloatingPointError("Non-finite output in the real demo dry run")
    result = dict(
        model_id=demo.MODEL_ID, device=model.bridge_device,
        use_pretrained=args.use_pretrained, mode="dry_run",
        model_loading=model.bridge_loading, load_seconds=load_seconds,
        forward_seconds=latency, sample_id=sample["identifier"],
        source_resolution=[512, 512], rgb_frames=16,
        latent_forward_only=True, full_video_pipeline=False, output=summary,
        execution="demo.predict with the same loaded model; no separate process or reload",
    )
    (HERE / "outputs").mkdir(exist_ok=True)
    write_json(HERE / "outputs/demo-result.json", result)
    write_json(HERE / ".status.json", {
        "status": "completed", "model_id": demo.MODEL_ID, "updated_at": now(),
        "stages": {"dry_run": {
            "status": "completed", "device": model.bridge_device,
            "npu_detected": str(model.bridge_device).startswith("npu"),
            "cuda_detected": False, "use_pretrained": args.use_pretrained,
            "real_forward": True, "output_finite": True,
            "sample_id": sample["identifier"], "result": "outputs/demo-result.json",
        }},
    })
    text = "[Device] " + str(model.bridge_device) + "\n"
    text += "[Scope] Real original full backbone dry-run; frozen inference, latent output\n"
    text += json.dumps(result) + "\n[Success] Real complete-backbone dry-run finished\n"
    (HERE / "output.txt").write_text(text)
    print(text, flush=True)
    del output
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-pretrained", action="store_true", help="Load demo's real from_pretrained / strict state loading; failure is fatal")
    parser.add_argument("--max-samples", type=int, default=250)
    parser.add_argument("--cpu", action="store_true", help="Explicit CPU reference; never automatic fallback")
    parser.add_argument("--profile-level", choices=["L0", "L1", "L2"], default="L0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timestep", type=int, default=500)
    parser.add_argument("--deadline-epoch", type=float, default=float(os.environ.get("BRIDGE_BENCHMARK_DEADLINE_EPOCH", 0)))
    args = parser.parse_args()
    runtime.prepare_paths()
    status = {"status": "running", "stage": "initializing", "start_time": now(), "num_samples": 0}
    write_json(HERE / ".benchmark-status.json", status)
    start_wall = time.perf_counter()
    try:
        if args.max_samples <= 0:
            raise ValueError("--max-samples must be positive")
        identifiers = list(demo.sample_ids())[:args.max_samples]
        if not identifiers or len(set(identifiers)) != len(identifiers):
            raise ValueError("Input sample IDs must be nonempty and distinct")
        if len(identifiers) < 50:
            raise ValueError("Official completed gate needs 50 distinct real samples; input has fewer")
        torch.manual_seed(args.seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
        device = runtime.select_device(args.cpu)
        if str(device).startswith("npu"):
            torch.npu.manual_seed_all(args.seed)
            torch.npu.empty_cache()
        status.update(stage="loading", device=device, use_pretrained=args.use_pretrained)
        write_json(HERE / ".benchmark-status.json", status)
        check_deadline(args)
        load_start = time.perf_counter()
        if args.use_pretrained:
            # demo.load_model loads real weights (from_pretrained or strict=True).
            model = demo.load_model(device)
        else:
            model = load_config_model(device)
        demo.synchronize(device)
        load_seconds = time.perf_counter() - load_start
        model.eval().requires_grad_(False)
        if any(str(p.device) != str(device) for p in model.parameters()):
            raise RuntimeError("A model parameter is outside the explicitly selected device")
        if args.use_pretrained:
            loading = model.bridge_loading
            if loading.get("missing_keys") != 0 or loading.get("unexpected_keys") != 0:
                raise RuntimeError("Pretrained model loading is not strict and complete")
        dtype_str = get_dtype_str(next(model.parameters()).dtype)
        mode_str = "pretrained" if args.use_pretrained else "config"
        dataset_name = "hdtf50_512x512"
        device_str = str(device).replace(":", "_")
        suffix = f"{device_str}_{dtype_str}_{mode_str}_{dataset_name}"
        trace_path = HERE / f"trace_{suffix}.json"
        metrics_path = HERE / f"benchmark_metrics_{device_str}_{dtype_str}_{mode_str}_{dataset_name}.json"
        outputs_path = HERE / f"outputs_{device_str}_{dtype_str}_{mode_str}_{dataset_name}.pt"
        status.update(stage="demo_dry_run", model_loading=model.bridge_loading)
        write_json(HERE / ".benchmark-status.json", status)
        first_sample = demo.load_sample(0)
        dry_result = run_demo_dry_run(model, first_sample, args, load_seconds)

        # Step 1: two true warmups, one minimal real warmup trace, then 50 timings.
        status["stage"] = "warmup_and_trace"
        write_json(HERE / ".benchmark-status.json", status)
        warmup_latencies = []
        for iteration in range(2):
            context = profiler_context(device, args.profile_level) if iteration == 1 else nullcontext()
            with context as profiler:
                value, latency = timed_predict(model, first_sample, args)
            if not bool(torch.isfinite(value).all()):
                raise FloatingPointError("Non-finite warmup output")
            warmup_latencies.append(latency)
            del value
            if iteration == 1:
                profiler.export_chrome_trace(str(trace_path))
        if str(device).startswith("npu"):
            torch.npu.reset_peak_memory_stats()
        status["stage"] = "measuring_50_real_samples"
        write_json(HERE / ".benchmark-status.json", status)
        outputs = []
        latencies = []
        (HERE / "outputs/measured-samples.jsonl").write_text("")
        measured_start = time.perf_counter()
        for index, identifier in enumerate(identifiers):
            sample = first_sample if index == 0 else demo.load_sample(index)
            if sample["identifier"] != identifier:
                raise ValueError("Manifest ID and loaded sample ID differ")
            value, latency = timed_predict(model, sample, args)
            summary = runtime.tensor_summary(value)
            if not summary["finite"]:
                raise FloatingPointError(f"Non-finite measured output: {identifier}")
            outputs.append({
                "sample_id": identifier, "prompt": identifier,
                "latent_shape": summary["shape"], "latent_mean": summary["mean"],
                "latent_std": summary["std"], "latent_min": summary["minimum"],
                "latent_max": summary["maximum"], "finite": summary["finite"],
                "selected_values": summary["selected_values"], "latency_s": latency,
            })
            latencies.append(latency)
            del value, sample
            status["num_samples"] = len(outputs)
            write_json(HERE / ".benchmark-status.json", status)
            with (HERE / "outputs/measured-samples.jsonl").open("a") as stream:
                stream.write(json.dumps(outputs[-1], allow_nan=False) + "\n")
            print(f"[Measured] {len(outputs)}/{len(identifiers)} sample={identifier} latency_s={latency:.6f}", flush=True)
        measured_wall_s = time.perf_counter() - measured_start
        if len(outputs) < 50 or not trace_path.is_file():
            raise RuntimeError("Insufficient actual outputs or missing real profiler trace")
        metrics = {
            "model_id": demo.MODEL_ID, "device": str(device), "dtype": dtype_str,
            "mode": mode_str, "dataset": dataset_name, "num_samples": len(outputs),
            "sample_ids": identifiers, "source_resolution": [512, 512], "rgb_frames": 16,
            "output_type": "transformer_hidden_states", "latency_s": statistics.mean(latencies),
            "latencies_s": latencies, "median_latency_s": statistics.median(latencies),
            "minimum_latency_s": min(latencies), "maximum_latency_s": max(latencies),
            "warmup_iterations": 2, "warmup_latencies_s": warmup_latencies,
            "trace_profile_level": args.profile_level, "trace_forward_count": 1,
            "trace_file": trace_path.name, "model_load_seconds": load_seconds,
            "start_time": status["start_time"], "end_time": now(),
            "wall_clock_s": time.perf_counter() - start_wall, "measured_wall_clock_s": measured_wall_s,
            "ttft_ms": None, "tpot_ms": None,
            "latency_measurement_scope": "device-synchronized demo.predict, includes input transfers/noise/conditioning/model; excludes disk sample read and output summaries",
            "quality_metric": None, "independent_accuracy_evaluation": False,
            "cpu_fallback_audit": "not independently evaluated; device placement checked, profiler retained for operator inspection",
            "cross_device_accuracy_evaluation": "not evaluated; no matching CUDA reference in this trial",
            "workload": "single timestep of full original frozen pretrained backbone; 50 distinct real HDTF latent caches; no decoding or full video",
            "outputs_reuse_measured_forwards": True, "full_video_pipeline": False,
            "all_outputs_finite": all(item["finite"] for item in outputs),
            "model_loading": model.bridge_loading, "dry_run": dry_result,
            "python_executable": sys.executable, "python_version": sys.version,
            "package_versions": package_versions(), "hardware": hardware_info(device),
            "scenario_command": [sys.executable, *sys.argv],
            "seed": args.seed, "timestep": args.timestep,
            "task_queue_enable": os.environ.get("TASK_QUEUE_ENABLE"),
            "attention_adapter_calls": getattr(runtime, "attention_calls", None),
            **memory_metrics(device),
        }
        write_json(metrics_path, metrics)

        # Step 2: no second pass; serialize small statistics from the SAME 50 outputs.
        status["stage"] = "saving_statistics"
        write_json(HERE / ".benchmark-status.json", status)
        torch.save({
            "diffusion_outputs": outputs, "latencies": latencies,
            "avg_latency": statistics.mean(latencies), "sample_ids": identifiers,
            "output_scope": metrics["workload"], "statistics_from_step1_same_forwards": True,
            "independent_quality_accuracy_metric": None,
        }, outputs_path)
        status.update(status="completed", stage="completed", end_time=now(),
                      metrics_file=metrics_path.name, outputs_file=outputs_path.name,
                      trace_file=trace_path.name, num_samples=len(outputs))
        write_json(HERE / ".benchmark-status.json", status)
        print(json.dumps(status), flush=True)
        return 0
    except BaseException as exc:
        status.update(status="failed", end_time=now(), exception_type=type(exc).__name__,
                      exception=str(exc), traceback=traceback.format_exc())
        write_json(HERE / ".benchmark-status.json", status)
        with (HERE / "output.txt").open("a") as stream:
            stream.write("\n[Benchmark failure]\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
