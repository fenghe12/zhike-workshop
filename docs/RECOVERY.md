# Recovery with persistent storage

English | [简体中文](RECOVERY.zh-CN.md) · [Project home](../README.md)

## Local application

1. Clone the repository, copy `.env.example` to `.env`, and select a writable runtime directory on persistent storage.
2. Install Python 3.13, Node.js, FFmpeg, and LibreOffice. Run `bash scripts/setup-local.sh`.
3. Configure the reference audio, reference image, Whisper small model, and CJK font paths. Supply your own reference media. Personal reference media is excluded from the public repository.
4. Run `bash scripts/start-local.sh` and open `http://127.0.0.1:18770`. Application data, outputs, and logs are stored in the runtime directory.

## Huawei Cloud Ascend 910B

The validated configuration uses PyTorch 2.7.1 / torch_npu 2.7.1, Python 3.11, CANN 8.3 RC1, and ARM64. The cloud image is `pytorch_2.7.1-cann_8.3.rc1-py_3.11-hce_2.0.2509-aarch64-snt9b`.

Confirm that the EVS volume is mounted at `/home/ma-user/work` and writable before restoring `npu-migration` and `smartcourse` beneath it. Store models, Python environments, CANN, caches, temporary files, build directories, and logs on that volume.

The private OBS backup contains the original source archive, models, and a working CANN runtime archive. Object locations are listed in `recovery/models.json`. Supply the bucket name and access credentials through your local environment. Access credentials are excluded from the public repository.

Use `scripts/restore-obs.py` with `--group code` or `--group qwen` to download the corresponding files. The source archive also contains other baseline implementations listed in `recovery/catalogs`. Those catalogs record restored sources. They do not indicate that every baseline has completed inference on the current hardware.

After restoring the original source archive into `npu-migration`, apply `recovery/npu-overlay` to the matching directory structure. Preserve the original third-party licenses. The current NPU adaptations are also stored separately in this repository.

CosyVoice and FlashHead use separate dependency directories. The tested CosyVoice configuration requires transformers 4.51.3 and tokenizers 0.21.1. FlashHead uses 4.57.3 and 0.22.1, respectively. Recorded versions are available in `recovery/environment-versions.json`. Do not install the legacy combined dependency list into both model environments.

The Qwen language model runs on the NPU, while its vision projection module runs on the CPU. `recovery/huawei/start_qwen36_npu.sh` contains the validated launch parameters. CANN 8.3 requires removing an unused recurrent gated delta rule header reference, setting up the OPP data link, and preloading the matching ARM64 `liboptiling.so`. The preserved source modifications and build scripts are in `recovery/huawei`.

The longer course workflow uses a 16,384-token context and schema-constrained output for PPT text segments. Uploaded presentations retain their original picture positions. The CosyVoice overlay reconstructs the waveform with CPU ISTFT to avoid an NPU operator failure on longer utterances. Its neural inference still runs on the NPU.

The local launcher defaults to one translation worker and one avatar worker, matching the single-NPU course run. The source narration and selected captions received manual review before final delivery. The validation record describes the tested scope and does not claim unattended processing of arbitrary course materials.

The Notebook SSH port may change after a restart. Update `remote-state.json` in the runtime directory with the current endpoint, following `config/remote-state.example.json`. Set the status to `RUNNING` only when the platform confirms that the instance is running.

Forward cloud port 7812 to local port 17813 over SSH and use the local Qwen endpoint configured in `.env`. Configure the remote CosyVoice and FlashHead paths there as well. The application uses logical device `npu:0`. The Notebook environment determines the physical device assignment for each session.

## Costs and retained data

EVS volumes and OBS storage may continue to incur charges after Notebook compute is stopped. Both CPU and NPU instances were stopped at the end of the October 21, 2026 acceptance session. The repository scripts do not automatically create, start, or delete cloud resources.

GitHub stores the code and recovery instructions. Private OBS stores large models, runtime archives, and generated outputs. Reusing the same cloud image still requires installing or restoring dependencies. The complete recovery process has not been validated again on a new, empty instance.

For the following download examples, first source `scripts/persistent-env.sh` and install `requirements/recovery.txt`:

```bash
python scripts/restore-obs.py --group code --destination /path/to/persistent/archives
python scripts/restore-obs.py --group course-models --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group qwen --destination /home/ma-user/work/npu-migration
python scripts/configure-npu.py
```

The download tool only downloads files. Before extraction, inspect the archive layout with `tar -tzf`. Restore the original archive into the appropriate directories, then extract the newer runtime archives. The original code backup excludes environment directories. Copy the matching base environment from the cloud image to EVS and install the recorded dependencies before configuring or starting the model services.
