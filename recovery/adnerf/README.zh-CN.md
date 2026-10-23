# AD-NeRF 官方预训练模型的昇腾部署

[English](README.md) | 简体中文

本部署使用 [AD-NeRF 官方](https://github.com/YudongGuo/AD-NeRF)提供的 Obama 头部与躯干预训练模型，未训练新人物。重建案例保留 300 帧、450 × 450 分辨率、25 FPS、64 个粗采样点、128 个重要性采样点及 `render_factor=0`。

音频使用官方 DeepSpeech 0.1.0 冻结模型及特征提取程序，原始音频产生有限且随时间变化的 `(7999, 16, 29)` 数组。单独的 MFCC 特征无法替代该数组。相机姿态沿用官方预训练模型提供的文件。背景使用官方人脸分割模型和原始第 4 步算法，保留该算法按原始步长 20 选取的全部 400 帧。

`patch_npu.py` 修改设备位置、旧版张量构造方法和 NumPy 已移除的类型别名，并要求头部、躯干检查点存在，记录实际加载的训练步数。两个检查点均放在组合渲染配置要求的 `dataset/Obama/logs/Obama_com` 目录。网络结构、光线采样参数和帧数保持不变。

[短程训练工具](training/README.zh-CN.md)提供完整训练图像生成、梯度与参数更新记录、检查点续训功能。实际完成的训练范围与预训练模型推理分别记录。

## 恢复已验证的环境

确认 `/home/ma-user/work/npu-migration` 所在持久卷已挂载且可写。基础 Python 3.11、PyTorch 2.7.1、torch_npu 2.7.1、CANN 和 `npu-shims` 按[恢复说明](../../docs/RECOVERY.zh-CN.md)准备。按该说明配置私有 OBS 访问后执行：

```bash
python scripts/restore-obs.py --group adnerf --destination /home/ma-user/work/npu-migration
cd /home/ma-user/work/npu-migration
tar -xzf adnerf-code-models-and-env.tar.gz
source scripts/persistent-npu-env.sh
bash scripts/python-adnerf-audio recovery/adnerf-official-20261023/extract_audio.py \
  --source repos/AD-NeRF-official-20261023 \
  --audio workspace/adnerf-official-20261023/Obama/aud.wav \
  --graph recovery/adnerf-official-20261023/models/deepspeech-0.1.0.pb \
  --output workspace/adnerf-official-20261023/Obama/aud.npy
python recovery/adnerf-official-20261023/run_native_case.py
```

音频特征提取使用 CPU TensorFlow，人脸分割与 NeRF 渲染在同一张昇腾卡上顺序执行。已有背景记录时，控制程序复用已生成的背景。在已验证设备上，渲染约需 50 分钟，准备过程另计。控制程序将完整 300 帧与原始音频合成为 12 秒 MP4，并检查帧数、分辨率、帧率和音轨。

环境、缓存、编译文件、日志与临时文件均通过 `persistent-npu-env.sh` 配置到持久化目录，恢复时保留该配置。权重和环境二进制文件保存在私有 OBS，本公开目录保存脚本、配置和资源位置。恢复对象见 `obs-objects.json`，实际完成范围见[部署记录](../../docs/deployment-20261023-adnerf.json)。
