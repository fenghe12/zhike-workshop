from pathlib import Path
path=Path('/home/ma-user/work/npu-migration/repos/SenseNova-U1-NPU/src/sensenova_u1/models/neo_unify/modeling_qwen3.py')
text=path.read_text()
old="torch.where(mask[None, None, :, :] > 0, torch.tensor(0.0), torch.tensor(float('-inf')))"
new="torch.where(mask[None, None, :, :] > 0, mask.new_zeros((), dtype=torch.float32), mask.new_full((), float('-inf'), dtype=torch.float32))"
if new not in text:
    assert old in text;text=text.replace(old,new);path.write_text(text)
path=path.parent/'transformers_compat.py';text=path.read_text()
old='    from transformers.utils.generic import check_model_inputs as model_input_compat'
new='''    from transformers.utils.generic import check_model_inputs

    def model_input_compat(func: Callable[..., Any]) -> Callable[..., Any]:
        return check_model_inputs()(func)'''
if new not in text:
    assert old in text;text=text.replace(old,new);path.write_text(text)
print('SenseNova attention-mask constants use the input device.',flush=True)
