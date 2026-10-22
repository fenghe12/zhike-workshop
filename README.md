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

## Rights and licenses

No repository-wide open-source license has been granted at this time. Third-party code and models remain subject to their respective licenses. Preserve the original licenses when restoring their source. Public access does not grant unrestricted redistribution rights.

## Development checks

```bash
cd backend/smartcourse
python -m unittest tests.test_course_api tests.test_remote_media_status tests.test_translation_policy tests.test_speech_timing tests.test_pptx_translation tests.test_deeppresenter_course tests.test_topic_source_language
cd ../../vue-app
npm run build
```

On October 23, 2026, these 27 backend tests passed. The unchanged frontend last passed its build on October 21. A new machine still requires the dependencies and models described in the recovery guide.
