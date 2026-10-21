from pathlib import Path
import shutil


root = Path("/home/ma-user/work/npu-migration")
recovery = root / "recovery/run-20261021/npu-correction"
sample = root / "repos/Latte/sample/sample_t2x.py"
source = sample.read_text()
before = 'tokenizer = T5Tokenizer.from_pretrained(args.pretrained_model_path, subfolder="tokenizer")'
after = 'tokenizer = load_latte_tokenizer(args.pretrained_model_path)'
if before in source:
    backup = recovery / "sample_t2x.before_tokenizer.py"
    if not backup.exists():
        shutil.copy2(sample, backup)
    source = source.replace(before, after, 1)
    source = source.replace(
        "from transformers import T5EncoderModel, T5Tokenizer",
        "from transformers import T5EncoderModel, T5Tokenizer\nfrom latte_tokenizer_compat import load_latte_tokenizer",
        1,
    )
    sample.write_text(source)
elif after not in source:
    raise RuntimeError("Latte entry point differs from the inspected source")
shutil.copy2(recovery / "latte_tokenizer_compat.py", sample.parent / "latte_tokenizer_compat.py")
print("Latte tokenizer compatibility change applied")
