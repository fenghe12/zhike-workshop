# Real-weight latent-forward benchmark

Run from this adaptation directory with its own persistent uv environment:

```sh
uv run --no-sync --extra ascend python accuracy_run.py --use-pretrained --max-samples 50 --profile-level L0
```

The default `--max-samples` is 250; this fixed input manifest contains 50 distinct actual HDTF cases. Each cached input derives from 512 × 512 RGB data. The original complete frozen backbone and real pretrained weights are loaded once with strict missing/unexpected-key checks. The same in-memory model executes the demo dry-run, two warmups, and 50 single-timestep forwards. One warmup is recorded by the real CPU/NPU profiler; only small latent statistics are saved. The 50 outputs are not rendered videos, a held-out quality benchmark, or an independent accuracy metric. No cross-device CUDA comparison or independent CPU-fallback audit is performed.

Step 1 produces a real `trace_*.json` and synchronized `benchmark_metrics_*.json`. Step 2 serializes `outputs_*.pt` statistics from those same 50 measured forwards; it does not execute another 50 samples. Latency excludes sample disk reads and CPU output summaries, but includes the exact `demo.predict` input transfer, noise, condition preparation and complete model forward.

The explicit default config-only mode uses the unchanged complete model configuration with random weights. It never replaces a failed pretrained load. All failures retain the actual exception and traceback in `.benchmark-status.json`; `completed` requires at least 50 distinct finite real outputs and all three output artifacts. `.status.json` and `output.txt` refer to the actual demo forward and are separate from the complete benchmark status.

The official static check also tests the completed-artifact gate. Before a real NPU run it is expected to report missing NPU metrics; no substitute artifact is created to suppress that result:

```sh
uv run python benchmark/scripts/check_accuracy_run.py --adapt alibaba_pai_easyanimatev3_xl_2_inp_512x512
```
