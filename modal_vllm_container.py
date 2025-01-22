import subprocess
from pathlib import Path

import modal
from modal import App, Image, Mount, Secret, gpu
from download_llama import MODEL_NAME, MODELS_DIR

########## CONSTANTS ##########

MODEL_PATH = MODELS_DIR + '/' + MODEL_NAME

# define model for serving and path to store in modal container
SECONDS = 60  # for timeout

try:
    volume = modal.Volume.lookup("llamas", create_if_missing=False)
except modal.exception.NotFoundError:
    raise Exception("Download models first with modal run download_llama.py")


########## UTILS FUNCTIONS ##########


# def download_hf_model(model_dir: str, model_name: str):
#     """Retrieve model from HuggingFace Hub and save into
#     specified path within the modal container.

#     Args:
#         model_dir (str): Path to save model weights in container.
#         model_name (str): HuggingFace Model ID.
#     """
#     import os

#     from huggingface_hub import snapshot_download  # type: ignore
#     from transformers.utils import move_cache  # type: ignore

#     os.makedirs(model_dir, exist_ok=True)

#     snapshot_download(
#         model_name,
#         local_dir=model_dir,
#         # consolidated.safetensors is prevent error here: https://github.com/vllm-project/vllm/pull/5005
#         ignore_patterns=["*.pt", "*.bin", "consolidated.safetensors"],
#         token=os.environ["HF_TOKEN"],
#     )
#     move_cache()


########## IMAGE DEFINITION ##########

# define image for modal environment
vllm_image = (
    Image.debian_slim(python_version="3.12")
    .pip_install(
        [
            "vllm",
            "huggingface_hub",
            "hf-transfer",
            "ray",
            "transformers",
        ]
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)


########## APP SETUP ##########


app = App("cameron-vllm")

NO_GPU = 1
TOKEN = "super-secret-token"  # for demo purposes, for production, you can use Modal secrets to store token

# https://github.com/chujiezheng/chat_templates/tree/main/chat_templates
LOCAL_TEMPLATE_PATH = "template_llama3.jinja"

@app.function(
    image=vllm_image,
    gpu=gpu.A100(count=NO_GPU, size="80GB"),
    container_idle_timeout=20 * SECONDS,
    volumes={MODELS_DIR: volume},
    mounts=[
        Mount.from_local_file(
            LOCAL_TEMPLATE_PATH, remote_path="/root/template_llama3.jinja"
        )
    ],
    # https://modal.com/docs/guide/concurrent-inputs
    concurrency_limit=1,  # fix at 1 to test concurrency within 1 server setup
    allow_concurrent_inputs=256,  # max concurrent input into container
)
@modal.web_server(port=8000, startup_timeout=60 * SECONDS)
def serve():
    cmd = f"""
    python -m vllm.entrypoints.openai.api_server --model {MODEL_PATH} \
        --max-model-len 24000 \
        --tensor-parallel-size {NO_GPU} \
        --trust-remote-code \
        --chat-template /root/template_llama3.jinja
    """
    print(cmd)
    subprocess.Popen(cmd, shell=True)