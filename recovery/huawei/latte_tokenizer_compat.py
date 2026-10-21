import json
from pathlib import Path

from transformers import T5Tokenizer


def load_latte_tokenizer(model_path):
    directory = Path(model_path) / "tokenizer"
    config = json.loads((directory / "tokenizer_config.json").read_text())
    keys = (
        "eos_token", "unk_token", "pad_token", "extra_ids",
        "additional_special_tokens", "sp_model_kwargs", "model_max_length",
        "clean_up_tokenization_spaces",
    )
    tokenizer = T5Tokenizer(
        vocab_file=str(directory / "spiece.model"),
        **{key: config[key] for key in keys if key in config},
    )
    # T5 already defines these sentinel IDs. Do not add them a second time.
    for token, expected in json.loads((directory / "added_tokens.json").read_text()).items():
        actual = tokenizer.convert_tokens_to_ids(token)
        if actual != expected:
            raise ValueError(f"Token ID differs for {token}: {actual} != {expected}")
    tokenizer.sanitize_special_tokens()
    return tokenizer
