"""Neural Network Model definitions and ONNX Inference Wrapper.

This module provides the tiny MLP architecture for GPU training on Modal
and the ONNX Runtime wrapper for CPU inference during Kaggle evaluation.
"""

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


# ---- PyTorch Model (for Modal Training) ----

if TORCH_AVAILABLE:
    class LightWeightMCTSNet(nn.Module):
        """A tiny MLP designed for sub-millisecond CPU inference.
        
        Predicts:
        - Value: probability of winning [-1, 1]
        - Policy: logits for the token action space
        """
        def __init__(self, state_dim: int, num_tokens: int, hidden_dim: int = 128):
            super().__init__()
            self.state_dim = state_dim
            self.num_tokens = num_tokens
            
            # Shared body
            self.fc1 = nn.Linear(state_dim, hidden_dim)
            self.fc2 = nn.Linear(hidden_dim, hidden_dim)
            
            # Value head
            self.val_fc = nn.Linear(hidden_dim, 32)
            self.val_out = nn.Linear(32, 1)
            
            # Policy head
            self.pol_fc = nn.Linear(hidden_dim, 64)
            self.pol_out = nn.Linear(64, num_tokens)

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            x = F.relu(self.fc1(x))
            x = F.relu(self.fc2(x))
            
            # Value in [-1, 1]
            val = F.relu(self.val_fc(x))
            val = torch.tanh(self.val_out(val))
            
            # Policy logits
            pol = F.relu(self.pol_fc(x))
            pol = self.pol_out(pol)
            
            return pol, val


# ---- ONNX Wrapper (for Kaggle CPU Inference) ----

class ONNXEvaluator:
    """Wrapper to run fast CPU inference on the ONNX model."""
    
    def __init__(self, model_path: str):
        if not ONNX_AVAILABLE:
            raise ImportError("onnxruntime is not installed. Cannot run ONNXEvaluator.")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found at {model_path}")
            
        # Optimization options for CPU inference
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.session = ort.InferenceSession(model_path, sess_options, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self.pol_name = self.session.get_outputs()[0].name
        self.val_name = self.session.get_outputs()[1].name

    def evaluate(self, state_features: np.ndarray) -> tuple[np.ndarray, float]:
        """Evaluates a single state.
        
        Args:
            state_features: 1D numpy array of shape (state_dim,)
            
        Returns:
            policy_logits: 1D numpy array of shape (num_tokens,)
            value: float in [-1, 1]
        """
        # Add batch dimension
        x = state_features.reshape(1, -1).astype(np.float32)
        outputs = self.session.run([self.pol_name, self.val_name], {self.input_name: x})
        
        pol_logits = outputs[0][0]
        value = float(outputs[1][0][0])
        return pol_logits, value
