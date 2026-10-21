from pathlib import Path
import shutil


root = Path("/home/ma-user/work/npu-migration")
source_file = root / "repos/llama.cpp/ggml/src/ggml-cann/aclnn_ops.cpp"
recovery = root / "recovery/run-20261021/npu-correction"
source = source_file.read_text()
header = "#include <aclnnop/aclnn_recurrent_gated_delta_rule.h>\n"
remaining = source.replace(header, "")
if "RecurrentGatedDeltaRule" in remaining:
    raise RuntimeError("The newer API is used; removing its include would be insufficient")
if header in source:
    backup = recovery / "aclnn_ops.before_cann83.cpp"
    if not backup.exists():
        shutil.copy2(source_file, backup)
    source_file.write_text(remaining)
print("Unused CANN header reference removed; build and NPU inference still required")
