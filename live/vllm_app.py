"""OpenAI-compatible vLLM server for Gemma 4 31B on one Modal H100.

Same model and vLLM pin as the competition Colab driver. One container at most, scales to zero
after 15 idle minutes. The API key comes from the local env (VLLM_API_KEY) as a Modal secret.
Deploy: VLLM_API_KEY=... modal deploy vllm_app.py ; stop: modal app stop g4-vllm
"""
import os
import subprocess

import modal

MODEL = 'google/gemma-4-31B-it-qat-w4a16-ct'
image = (modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04', add_python='3.12')
         # pins from the competition Colab driver; an unpinned transformers breaks vllm 0.19.1 config parsing
         .uv_pip_install('vllm==0.19.1', 'compressed-tensors==0.15.0.1', 'transformers==5.13.1',
                         'tokenizers==0.22.2', 'safetensors==0.8.0', 'flashinfer-python==0.6.6',
                         'flashinfer-cubin==0.6.6', 'huggingface_hub[hf_transfer]')
         .env({'HF_HUB_ENABLE_HF_TRANSFER': '1'}))
hf_cache = modal.Volume.from_name('hf-cache', create_if_missing=True)
vllm_cache = modal.Volume.from_name('vllm-cache', create_if_missing=True)
app = modal.App(os.environ.get('APP_NAME', 'g4-vllm'))  # APP_NAME=g4-vllm-b deploys a second server


@app.function(image=image, gpu='H100', max_containers=1, scaledown_window=15 * 60, timeout=4 * 3600,
              volumes={'/root/.cache/huggingface': hf_cache, '/root/.cache/vllm': vllm_cache},
              secrets=[modal.Secret.from_dict({'VLLM_API_KEY': os.environ.get('VLLM_API_KEY', '')})])
@modal.concurrent(max_inputs=64)
@modal.web_server(port=8000, startup_timeout=25 * 60)
def serve():
    subprocess.Popen(['vllm', 'serve', MODEL, '--served-model-name', 'gemma4', '--host', '0.0.0.0',
                      '--port', '8000', '--max-model-len', '65536', '--gpu-memory-utilization', '0.92',
                      '--max-num-seqs', '48', '--reasoning-parser', 'gemma4'])
