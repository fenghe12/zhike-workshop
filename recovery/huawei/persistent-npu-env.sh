#!/usr/bin/env bash
export NPU_ROOT=/home/ma-user/work/npu-migration
export TMPDIR="$NPU_ROOT/tmp" TEMP="$NPU_ROOT/tmp" TMP="$NPU_ROOT/tmp"
export XDG_CACHE_HOME="$NPU_ROOT/cache" PIP_CACHE_DIR="$NPU_ROOT/cache/pip"
export CONDA_PKGS_DIRS="$NPU_ROOT/cache/conda-pkgs" CONDA_ENVS_PATH="$NPU_ROOT/envs"
export HF_HOME="$NPU_ROOT/cache/huggingface" HF_HUB_CACHE="$NPU_ROOT/cache/huggingface/hub"
export HUGGINGFACE_HUB_CACHE="$HF_HUB_CACHE" TORCH_HOME="$NPU_ROOT/cache/torch"
export TORCH_EXTENSIONS_DIR="$NPU_ROOT/cache/torch-extensions" TRITON_CACHE_DIR="$NPU_ROOT/cache/triton"
export NUMBA_CACHE_DIR="$NPU_ROOT/cache/numba" MPLCONFIGDIR="$NPU_ROOT/cache/matplotlib"
export ASCEND_CACHE_PATH="$NPU_ROOT/cache/ascend" ASCEND_WORK_PATH="$NPU_ROOT/cache/ascend-work"
export ACL_OP_COMPILER_CACHE_DIR="$NPU_ROOT/cache/ascend/compiler"
export ASCEND_PROCESS_LOG_PATH="$NPU_ROOT/logs/ascend" ASCEND_SLOG_PRINT_TO_STDOUT=0
export PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8
export PATH="$NPU_ROOT/envs/npu-base/bin:$NPU_ROOT/bin:$NPU_ROOT/toolchains/ffmpeg/bin:$PATH"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR" "$HF_HUB_CACHE" "$TORCH_HOME" "$TORCH_EXTENSIONS_DIR" "$TRITON_CACHE_DIR" "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR" "$ASCEND_CACHE_PATH" "$ASCEND_WORK_PATH" "$ACL_OP_COMPILER_CACHE_DIR" "$ASCEND_PROCESS_LOG_PATH"
if [ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]; then
  source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi
if [ -f "$NPU_ROOT/toolchains/ascend-8.3rc1/lib64/libascendcl.so" ]; then
  export ASCEND_HOME_PATH="$NPU_ROOT/toolchains/ascend-8.3rc1"
  export ASCEND_OPP_PATH="$ASCEND_HOME_PATH/opp"
  export LD_LIBRARY_PATH="$ASCEND_HOME_PATH/aarch64-linux/lib64:$ASCEND_HOME_PATH/lib64:${LD_LIBRARY_PATH:-}"
  export PYTHONPATH="$ASCEND_HOME_PATH/python/site-packages:${PYTHONPATH:-}"
  export PATH="$ASCEND_HOME_PATH/bin:$ASCEND_HOME_PATH/compiler/ccec_compiler/bin:$PATH"
fi

export ASCEND_TOOLKIT_HOME="$ASCEND_HOME_PATH" ASCEND_AICPU_PATH="$ASCEND_HOME_PATH"
export ASCEND_AUTOML_PATH="$ASCEND_HOME_PATH/tools"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH//\/usr\/local\/Ascend\/ascend-toolkit\/latest/$ASCEND_HOME_PATH}"
export PYTHONPATH="${PYTHONPATH//\/usr\/local\/Ascend\/ascend-toolkit\/latest/$ASCEND_HOME_PATH}"
