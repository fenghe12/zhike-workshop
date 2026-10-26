# Smartcourse

English | [简体中文](README.zh-CN.md)

A course generation and multilingual avatar video system, with a Vue workbench, Python backend, WeChat Mini Program source, Ascend NPU adaptations, and recovery tools.

The main pipeline turns slides and lecture notes into translated content, speech, timed subtitles, avatars, and course videos. The source also includes course material management, task tracking, result downloads, and knowledge base features.

## Getting started

```bash
git clone https://github.com/fenghe12/zhike-workshop.git
cd zhike-workshop
cp .env.example .env
# Edit .env to point the runtime directory and model paths to persistent storage.
bash scripts/setup-local.sh
bash scripts/start-local.sh
```

Open `http://127.0.0.1:18770` to access the workbench. Full generation requires configured models and media services. See the [setup and recovery guide](docs/RECOVERY.md) for details.

## Repository structure

| Path | Contents |
| --- | --- |
| `backend/smartcourse` | Backend API, five-stage course pipeline, translation, speech, subtitles, video, and related tests |
| `vue-app` | Vue 3 / TypeScript workbench and npm dependency lockfile |
| `pages`, `services`, `utils` | WeChat Mini Program source |
| `ui-adapter` | Slide previews and frontend/backend integration |
| `scripts` | Persistent environment setup, installation, startup, and model/OBS downloads |
| `recovery` | Model inventory, dependency versions, NPU adaptations, build scripts, and launchers |

## Validation status

On October 21, 2026, six single-slide short courses were generated in Chinese, English, Japanese, Korean, German, and French. Checks covered translated titles, numeric values, subtitle coverage and timing, and video audio tracks. Results are recorded in the [acceptance report](docs/acceptance-20261021.json). Full-length courses were not retested in that session.

On October 22, a complete 12-slide Japanese opening lesson was generated from the source presentation, including translated slides, narration, 86 timed subtitles, avatar video, and final composition. The video lasts 10 minutes 4.8 seconds at 1920 × 1080. See the [course validation record](docs/acceptance-20261022.json). This covers the opening lesson, not the entire chapter or semester course.

The Qwen3.6 language model, CosyVoice3, and FlashHeadLite use Ascend 910B. FFmpeg composition and Whisper subtitle alignment run locally. Cloud compute was stopped after validation, with persistent disks and OBS backups retained.

On October 22–23, Qwen3.6 generated one eight-slide Chinese lesson, which was reviewed and then translated into English, Japanese, Korean, German, French, and Russian. All six translations used the same source deck. Checks covered the numeric example, AND truth table, threshold equality, remaining Chinese text, missing glyphs, complete rendered paragraphs, and page layouts. The [generation and translation record](docs/acceptance-20261022-generation-translation.json) lists the corrections and scope. This test used an editable title-and-content template and did not test audio, video, or browser interaction.

Model weights, Python environments, generated videos, login data, and personal reference media are excluded from Git. Large-file download sources and private OBS object locations are listed in `recovery/models.json`.

Additional [SenseNova U1.5 and AgentHOI recovery tools](recovery/sensenova-agenthoi/README.md) preserve the official inference cases and sampling defaults, with single-device Ascend compatibility changes and separate OBS model/runtime backups.

[Offline report video previews](recovery/reporting/README.md) keep videos and preview images embedded in one HTML file and preserve the original video data.

The [AD-NeRF recovery tools](recovery/adnerf/README.md) use the official pretrained Obama models, native DeepSpeech features and the original 300-frame reconstruction configuration on one Ascend device.

The [video training adapters](recovery/video-training/README.md) record bounded EasyAnimate V3 and Wan2.2 S2V training on one Ascend device, including backward passes, actual parameter updates, native conditional paths, and private checkpoint recovery.

The [DiTalker/CogPortrait adapters and records](recovery/ditalker-cogportrait/README.md) now include the [correct last-output-zero50-case/100-step run](recovery/ditalker-cogportrait/sessions/ditalker-gradient-repair-50hdtf-100steps-20261025/README.md): all11 added groups received nonzero gradients and changed parameters, and908/908 added tensors received gradients. The earlier all-parameter-zero initialization was a misunderstanding and is preserved as history. The local standalone report combines complete loss files, curves, diagnostics and actual previews. CogPortrait still covers its pose branch only.

The [Higher Education Press configuration archive](integrations/hep/README.md) preserves the existing agent prompt and historical plugin contract. It does not change the platform or redeploy a cloud endpoint.

The October 25 source update also includes account isolation, a persistent three-to-five-worker task queue with shared media slots, slide notes and font handling, subtitle wrapping, and the latest Korean/Japanese speech corrections. Teacher listening and final educational-content acceptance remain pending; see the dated recovery notes for the measured scope.

The October 27 update adds resumable mobile uploads, per-account browser drafts, password and email verification tools, material retention, generation estimates and bounded compute requests. All70 backend checks and the frontend build passed. Seven languages passed slide/narration and speech checks; new Russian and Spanish short-course videos were completed. The other five video languages were not regenerated in this session. Real email delivery awaits SMTP configuration. See the [product operations guide](docs/PRODUCT_OPERATIONS.md) and [validation scope](docs/acceptance-20261027-product.json).

## Rights and licenses

No repository-wide open-source license has been granted at this time. Third-party code and models remain subject to their respective licenses. Preserve the original licenses when restoring their source. Public access does not grant unrestricted redistribution rights.

## Development checks

```bash
cd backend/smartcourse
python -m unittest tests.test_app tests.test_pptx_notes tests.test_pptx_translation tests.test_translation_policy tests.test_speech_chunks tests.test_subtitle_validation
cd ../../vue-app
npm run build
```

On October 25, 2026, these 55 backend checks and the frontend production build passed. The archived DiTalker source patch was applied and compared directly with the executed source. A new machine still requires the dependencies and models described in the recovery guide.
