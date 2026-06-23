import os
import sys

# 1. 强行给 Python 3.13 指路，告诉它 c10.dll 在哪里
venv_base = os.path.dirname(os.path.dirname(sys.executable))
torch_lib_path = os.path.join(venv_base, 'Lib', 'site-packages', 'torch', 'lib')

if os.path.exists(torch_lib_path):
    print(f"✅ 找到底层 DLL 目录: {torch_lib_path}")
    os.add_dll_directory(torch_lib_path) # 核心破解代码
else:
    print("❌ 找不到 Torch 的 lib 目录，请检查包是否安装完整")

# 2. 指路完毕后，再导入 torch
print("正在尝试唤醒 PyTorch...")
import torch

print(f"🎉 成功！CUDA可用状态: {torch.cuda.is_available()}")