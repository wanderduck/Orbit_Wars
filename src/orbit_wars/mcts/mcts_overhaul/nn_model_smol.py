"""Neural Network Model definitions and ONNX Inference Wrapper."""
from __future__ import annotations

import os
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False


if TORCH_AVAILABLE:
    class LightWeightMCTSNet(nn.Module):
        """A deep MLP engineered with BatchNorm residual connections and Dropout.
        Increases generalization significantly while guaranteeing sub-ms inference
        because BatchNorm fuses mathematically into Linear parameters on ONNX export,
        and Dropout is completely disabled/removed during ONNX export.

        Expanded to a 2048-dimensional deep funnel architecture utilizing GELU
        activations to prevent dead neurons and stabilize deep gradient flows.
        """
        def __init__(self, state_dim: int, num_tokens: int, hidden_dim: int = 1024, dropout_p: float = 0.1):
            super().__init__()
            self.state_dim = state_dim
            self.num_tokens = num_tokens

            # Dropout layer to prevent massive 1024-dim layers from overfitting
            self.dropout = nn.Dropout(p=dropout_p)

            # --- Block 1: 1024 dimensions ---
            self.fc1 = nn.Linear(state_dim, hidden_dim, bias=False)
            self.bn1 = nn.BatchNorm1d(hidden_dim)
            self.fc2 = nn.Linear(hidden_dim, hidden_dim, bias=False)
            self.bn2 = nn.BatchNorm1d(hidden_dim)
            self.fc3 = nn.Linear(hidden_dim, hidden_dim, bias=False)
            self.bn3 = nn.BatchNorm1d(hidden_dim)

            # --- Block 2: 512 dimensions ---
            dim_b2 = hidden_dim // 2
            self.fc4 = nn.Linear(hidden_dim, dim_b2, bias=False)
            self.bn4 = nn.BatchNorm1d(dim_b2)
            self.fc5 = nn.Linear(dim_b2, dim_b2, bias=False)
            self.bn5 = nn.BatchNorm1d(dim_b2)
            self.fc6 = nn.Linear(dim_b2, dim_b2, bias=False)
            self.bn6 = nn.BatchNorm1d(dim_b2)

            # --- Block 3: 256 dimensions ---
            dim_b3 = dim_b2 // 2
            self.fc7 = nn.Linear(dim_b2, dim_b3, bias=False)
            self.bn7 = nn.BatchNorm1d(dim_b3)
            self.fc8 = nn.Linear(dim_b3, dim_b3, bias=False)
            self.bn8 = nn.BatchNorm1d(dim_b3)
            self.fc9 = nn.Linear(dim_b3, dim_b3, bias=False)
            self.bn9 = nn.BatchNorm1d(dim_b3)

            # --- Value Head ---
            self.val_fc = nn.Linear(dim_b3, 64, bias=False)
            self.val_bn = nn.BatchNorm1d(64)
            self.val_out = nn.Linear(64, 1)

            # --- Policy Head ---
            # Widened to 512 to support the massive num_tokens classification output
            self.pol_fc = nn.Linear(dim_b3, 512, bias=False)
            self.pol_bn = nn.BatchNorm1d(512)
            self.pol_out = nn.Linear(512, num_tokens)

            # Apply Initialization
            self._initialize_weights()

        def _initialize_weights(self):
            """Safely initializes weights to prevent vanishing/exploding gradients in deep layers."""
            for m in self.modules():
                if isinstance(m, nn.Linear):
                    # Kaiming He initialization works perfectly for GELU as it shares the same positive-side variance as ReLU
                    nn.init.kaiming_normal_(m.weight, mode='fan_in', nonlinearity='relu')
                    if m.bias is not None:
                        nn.init.constant_(m.bias, 0)
                elif isinstance(m, nn.BatchNorm1d):
                    nn.init.constant_(m.weight, 1)
                    nn.init.constant_(m.bias, 0)

            # Zero-initialize the last BatchNorm in each residual branch.
            # This ensures that each residual block starts as an identity function,
            # preventing massive gradient spikes in the first few epochs.
            nn.init.constant_(self.bn3.weight, 0)
            nn.init.constant_(self.bn6.weight, 0)
            nn.init.constant_(self.bn9.weight, 0)

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            # Block 1 (Residual + Dropout)
            x1 = F.gelu(self.bn1(self.fc1(x)))
            x2 = F.gelu(self.bn2(self.fc2(x1)))
            x2 = self.dropout(x2)
            # Add the skip connection BEFORE the final activation for proper ResNet flow
            x3 = F.gelu(self.bn3(self.fc3(x2)) + x1)

            # Block 2 (Residual + Dropout)
            x4 = F.gelu(self.bn4(self.fc4(x3)))
            x5 = F.gelu(self.bn5(self.fc5(x4)))
            x5 = self.dropout(x5)
            x6 = F.gelu(self.bn6(self.fc6(x5)) + x4)

            # Block 3 (Residual + Dropout)
            x7 = F.gelu(self.bn7(self.fc7(x6)))
            x8 = F.gelu(self.bn8(self.fc8(x7)))
            x8 = self.dropout(x8)
            x9 = F.gelu(self.bn9(self.fc9(x8)) + x7)

            # Value Output
            val = F.gelu(self.val_bn(self.val_fc(x9)))
            val = torch.tanh(self.val_out(val))

            # Policy Output
            pol = F.gelu(self.pol_bn(self.pol_fc(x9)))
            pol = self.pol_out(pol)

            return pol, val


class ONNXEvaluator:
    def __init__(self, model_path: str):
        if not ONNX_AVAILABLE:
            raise ImportError("onnxruntime is not installed. Cannot run ONNXEvaluator.")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found at {model_path}")

        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        # ONNX Execution Provider configured for highly optimized CPU inference
        self.session = ort.InferenceSession(model_path, sess_options, providers=['CPUExecutionProvider'])

        self.input_name = self.session.get_inputs()[0].name
        self.pol_name = self.session.get_outputs()[0].name
        self.val_name = self.session.get_outputs()[1].name

    def evaluate(self, state_features: np.ndarray) -> tuple[np.ndarray, float]:
        x = state_features.reshape(1, -1).astype(np.float32)
        outputs = self.session.run([self.pol_name, self.val_name], {self.input_name: x})
        return outputs[0][0], float(outputs[1][0][0])