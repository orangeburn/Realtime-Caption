# a4s/config.py

import os
import torch

# 本地 SenseVoice 仓库路径
SENSEVOICE_REPO = os.getenv(
    "SENSEVOICE_REPO",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../SenseVoice"))
)

# 翻译模型路径
TRANSLATION_MODEL_DIR = os.getenv(
    "TRANSLATION_MODEL_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../nllb200_ct2"))
)

# 设备设定：强制 CPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


