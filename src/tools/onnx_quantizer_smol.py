"""This script preprocesses the ***smol*** ONNX model weights output, then quantizes it."""


from pathlib import Path
from onnxruntime.quantization import quantize_dynamic, QuantType
from onnxruntime.quantization.shape_inference import quant_pre_process

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Define file paths
raw_model_path = str(REPO_ROOT / "models_smol" / "mcts_net.onnx")
preprocessed_model_path = str(REPO_ROOT / "models_smol" / "mcts_net_prep.onnx")
quantized_model_path = str(REPO_ROOT / "models_smol" / "mcts_net_quantized.onnx")

# 1. Pre-process the PyTorch-exported model to clear out conflicting shape metadata
quant_pre_process(
    input_model_path=raw_model_path,
    output_model_path=preprocessed_model_path,
    skip_optimization=False
)

# 2. Quantize the cleaned, pre-processed model
quantize_dynamic(
    model_input=preprocessed_model_path,
    model_output=quantized_model_path,
    weight_type=QuantType.QUInt8
)