"""OpenAI-compatible vLLM server for Gemma 4 E4B on one Modal L40S: the reason checker.

Same image and pins as vllm_app.py (copied, since Modal runs this file alone). Deploy: VLLM_API_KEY=... modal deploy vllm_small.py ;
stop: modal app stop g4-small
"""
import os
import subprocess

import modal

image = (modal.Image.from_registry('nvidia/cuda:12.8.1-devel-ubuntu22.04', add_python='3.12')
         .uv_pip_install('vllm==0.19.1', 'compressed-tensors==0.15.0.1', 'transformers==5.13.1',
                         'tokenizers==0.22.2', 'safetensors==0.8.0', 'flashinfer-python==0.6.6',
                         'flashinfer-cubin==0.6.6', 'huggingface_hub[hf_transfer]')
         .env({'HF_HUB_ENABLE_HF_TRANSFER': '1'}))
hf_cache = modal.Volume.from_name('hf-cache', create_if_missing=True)
vllm_cache = modal.Volume.from_name('vllm-cache', create_if_missing=True)

MODEL = 'google/gemma-4-E4B-it'
app = modal.App('g4-small')


@app.function(image=image, gpu='L40S', max_containers=1, scaledown_window=15 * 60, timeout=3 * 3600,
              volumes={'/root/.cache/huggingface': hf_cache, '/root/.cache/vllm': vllm_cache},
              secrets=[modal.Secret.from_dict({'VLLM_API_KEY': os.environ.get('VLLM_API_KEY', '')})])
@modal.concurrent(max_inputs=64)
@modal.web_server(port=8000, startup_timeout=25 * 60)
def serve():
    subprocess.Popen(['vllm', 'serve', MODEL, '--served-model-name', 'gemma4-e4b', '--host', '0.0.0.0',
                      '--port', '8000', '--max-model-len', '16384', '--gpu-memory-utilization', '0.90',
                      '--max-num-seqs', '32', '--limit-mm-per-prompt', '{"image": 0, "audio": 0}'])
