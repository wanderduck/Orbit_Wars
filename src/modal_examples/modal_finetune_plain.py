"""Fine-tune Gemma 4 E4B on Modal with A100-40GB GPU (no Unsloth).

Uses PEFT + TRL + BitsAndBytes for QLoRA fine-tuning directly,
bypassing Unsloth's dynamic patching. Exports LoRA adapters and
merges to GGUF via llama.cpp.

Usage:
    modal run deploy/modal_finetune_plain.py              # Run fine-tuning
    modal run deploy/modal_finetune_plain.py::download_results  # List output files
"""

import modal

MINUTES = 60

output_vol = modal.Volume.from_name("navigator-finetune-output", create_if_missing=True)

finetune_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "cmake", "build-essential")
    .pip_install(
        "torch",
        "torchvision",
        "peft",
        "accelerate",
        "bitsandbytes",
        "trl",
        "datasets",
        "sentencepiece",
        "protobuf",
        "rich",
        "scipy",
        # Gemma 4 requires unreleased transformers with gemma4 arch support
        "git+https://github.com/huggingface/transformers.git",
    )
    .run_commands(
        # Build llama.cpp for GGUF conversion
        "git clone https://github.com/ggerganov/llama.cpp /llama.cpp",
        "cd /llama.cpp && cmake -B build && cmake --build build --config Release -j$(nproc)",
        "pip install /llama.cpp/gguf-py",
    )
    .add_local_file("data/training/generated.jsonl", remote_path="/data/generated.jsonl", copy=True)
)

app = modal.App("navigator-finetune-plain", image=finetune_image)


@app.function(
    gpu="A100-40GB",
    timeout=180 * MINUTES,
    volumes={"/output": output_vol},
    secrets=[modal.Secret.from_name("huggingface")],
)
def finetune():
    """Run QLoRA fine-tuning with PEFT + TRL on A100."""
    import json
    import os
    import torch
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer
    from datasets import Dataset

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    import torch.nn as nn
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from transformers.models.gemma4 import modeling_gemma4
    from peft import get_peft_model

    model_name = "google/gemma-4-E4B-it"

    # --- Load model FIRST in bf16, before any patching ---
    # Must load before patching __bases__ because vision tower components
    # call Gemma4ClippableLinear(config) during construction, and nn.Linear
    # expects (in_features, out_features) — not a config object.
    print("Loading model in bf16...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        dtype=torch.bfloat16,
        attn_implementation="eager",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    print(f"Model loaded: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")

    # --- Patch Gemma4ClippableLinear AFTER model loading ---
    # Now all ClippableLinear instances are already constructed, so changing
    # __bases__ won't affect any __init__ calls. PEFT uses isinstance checks
    # to find nn.Linear layers for LoRA injection.
    _OrigClippable = modeling_gemma4.Gemma4ClippableLinear
    _OrigClippable.__bases__ = (nn.Linear,) + tuple(
        b for b in _OrigClippable.__bases__ if b is not nn.Module and b is not object
    )

    # ClippableLinear stores weights at self.linear.weight, but PEFT expects
    # self.weight directly (like nn.Linear). Add properties to delegate.
    _OrigClippable.weight = property(lambda self: self.linear.weight)
    _OrigClippable.bias = property(lambda self: self.linear.bias)
    _OrigClippable.in_features = property(lambda self: self.linear.in_features)
    _OrigClippable.out_features = property(lambda self: self.linear.out_features)
    print("Patched Gemma4ClippableLinear to inherit from nn.Linear (post-load)")

    # --- Load training data ---
    records = []
    with open("/data/generated.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    dataset = Dataset.from_dict({"messages": [r["messages"] for r in records]})
    print(f"Training examples: {len(dataset)}")

    # --- Apply LoRA via PEFT directly ---
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        exclude_modules=["vision_tower", "multi_modal_projector", "audio_tower"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # --- Training config ---
    training_args = SFTConfig(
        output_dir="/output/checkpoints",
        num_train_epochs=2,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=5,
        save_steps=50,
        save_total_limit=2,
        bf16=True,
        optim="adamw_8bit",
        seed=42,
        report_to="none",
        gradient_checkpointing=True,
        max_grad_norm=0.3,
        max_length=2048,
        packing=False,
    )

    # --- Train ---
    # Pass pre-loaded model object (already has LoRA applied).
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        train_dataset=dataset,
    )

    print("Starting training...")
    result = trainer.train()
    metrics = result.metrics
    print(f"Training complete! Loss: {metrics.get('train_loss', 'N/A'):.4f}")
    print(f"Runtime: {metrics.get('train_runtime', 0):.1f}s")

    # --- Save LoRA adapters ---
    trainer.save_model("/output/lora")
    print("LoRA adapters saved to /output/lora")

    # --- Merge LoRA into base model and save full model ---
    print("Merging LoRA adapters into base model...")
    merged_model = trainer.model.merge_and_unload()
    merged_model.save_pretrained("/output/merged", safe_serialization=True)
    trainer.processing_class.save_pretrained("/output/merged")
    print("Merged model saved to /output/merged")

    # --- Convert to GGUF ---
    os.makedirs("/output/gguf", exist_ok=True)
    print("Converting to GGUF (q4_k_m)...")
    convert_result = os.system(
        "python /llama.cpp/convert_hf_to_gguf.py /output/merged "
        "--outfile /output/gguf/model-f16.gguf --outtype f16"
    )
    if convert_result == 0:
        os.system(
            "/llama.cpp/build/bin/llama-quantize "
            "/output/gguf/model-f16.gguf /output/gguf/model-q4_k_m.gguf q4_k_m"
        )
        # Remove the large f16 intermediate
        if os.path.exists("/output/gguf/model-q4_k_m.gguf"):
            os.remove("/output/gguf/model-f16.gguf")
            print("GGUF q4_k_m exported to /output/gguf/model-q4_k_m.gguf")
        else:
            print("WARNING: Quantization may have failed, keeping f16 GGUF")
    else:
        print("WARNING: HF-to-GGUF conversion failed. LoRA adapters still available at /output/lora")

    # --- Create Ollama Modelfile ---
    gguf_files = [f for f in os.listdir("/output/gguf") if f.endswith(".gguf")]
    if gguf_files:
        gguf_filename = gguf_files[0]
        system_prompt = (
            "You are NorthStar Navigator, a plain-language government benefits navigator for Minnesota. "
            "You help people understand which government assistance programs they may "
            "be eligible for based on their situation. Be warm, clear, and actionable. "
            "Always cite specific eligibility thresholds and application portals. "
            'Never say someone "qualifies" — say "may be eligible." '
            "End every response with a disclaimer that this is informational, not legal advice."
        )
        modelfile = f"""FROM ./{gguf_filename}
PARAMETER temperature 1.0
PARAMETER top_p 0.95
PARAMETER num_ctx 2048
SYSTEM "{system_prompt}"
"""
        with open("/output/gguf/Modelfile", "w") as f:
            f.write(modelfile)
        print("Modelfile written.")

    # --- Test inference ---
    print("\n--- Test Inference ---")
    model = trainer.model
    tokenizer = trainer.processing_class
    model.eval()
    test_messages = [{"role": "user", "content":
        "I'm a single mom with two kids ages 3 and 7. I just lost my job "
        "last week and I live in Hennepin County. What help is available?"}]

    inputs = tokenizer.apply_chat_template(
        test_messages, tokenize=True, add_generation_prompt=True, return_tensors="pt",
        return_dict=True,
    )
    input_ids = inputs["input_ids"].to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids, max_new_tokens=512,
            temperature=1.0, top_p=0.95, do_sample=True,
        )
    response = tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)
    print(response[:500])

    # Commit volume
    output_vol.commit()

    # List outputs
    for root, dirs, files in os.walk("/output"):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path) / 1024 / 1024
            print(f"  {path} ({size:.1f} MB)")

    print("\nDone! Run `modal run deploy/modal_finetune_plain.py::download_results` to download.")


@app.function(
    gpu="A100-40GB",
    volumes={"/output": output_vol},
    timeout=60 * MINUTES,
    secrets=[modal.Secret.from_name("huggingface")],
)
def convert_gguf():
    """Load base model + LoRA adapters, merge, convert to GGUF, and test."""
    import os
    import torch
    import torch.nn as nn
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from transformers.models.gemma4 import modeling_gemma4
    from peft import PeftModel

    if not os.path.exists("/output/lora"):
        print("ERROR: /output/lora not found. Run finetune first.")
        return

    # --- Load base model + LoRA adapters and merge ---
    model_name = "google/gemma-4-E4B-it"
    print("Loading base model...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name, device_map="auto", dtype=torch.bfloat16, trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

    # Patch ClippableLinear (same as training) so PEFT can load adapters
    _Orig = modeling_gemma4.Gemma4ClippableLinear
    _Orig.__bases__ = (nn.Linear,) + tuple(
        b for b in _Orig.__bases__ if b is not nn.Module and b is not object
    )
    _Orig.weight = property(lambda self: self.linear.weight)
    _Orig.bias = property(lambda self: self.linear.bias)
    _Orig.in_features = property(lambda self: self.linear.in_features)
    _Orig.out_features = property(lambda self: self.linear.out_features)

    print("Loading LoRA adapters...")
    model = PeftModel.from_pretrained(model, "/output/lora")
    print("Merging LoRA into base model...")
    model = model.merge_and_unload()

    # Save merged model properly (model + tokenizer)
    import shutil
    if os.path.exists("/output/merged"):
        shutil.rmtree("/output/merged")
    model.save_pretrained("/output/merged", safe_serialization=True)
    tokenizer.save_pretrained("/output/merged")
    print("Merged model saved to /output/merged")

    # --- Convert to GGUF ---
    os.makedirs("/output/gguf", exist_ok=True)
    print("Converting to GGUF (q4_k_m)...")
    convert_result = os.system(
        "python /llama.cpp/convert_hf_to_gguf.py /output/merged "
        "--outfile /output/gguf/model-f16.gguf --outtype f16"
    )
    if convert_result == 0:
        os.system(
            "/llama.cpp/build/bin/llama-quantize "
            "/output/gguf/model-f16.gguf /output/gguf/model-q4_k_m.gguf q4_k_m"
        )
        if os.path.exists("/output/gguf/model-q4_k_m.gguf"):
            os.remove("/output/gguf/model-f16.gguf")
            print("GGUF q4_k_m exported to /output/gguf/model-q4_k_m.gguf")
        else:
            print("WARNING: Quantization may have failed, keeping f16 GGUF")
    else:
        print("WARNING: HF-to-GGUF conversion failed.")

    # --- Create Ollama Modelfile ---
    gguf_files = [f for f in os.listdir("/output/gguf") if f.endswith(".gguf")]
    if gguf_files:
        gguf_filename = gguf_files[0]
        system_prompt = (
            "You are NorthStar Navigator, a plain-language government benefits navigator for Minnesota. "
            "You help people understand which government assistance programs they may "
            "be eligible for based on their situation. Be warm, clear, and actionable. "
            "Always cite specific eligibility thresholds and application portals. "
            'Never say someone "qualifies" — say "may be eligible." '
            "End every response with a disclaimer that this is informational, not legal advice."
        )
        modelfile = f"""FROM ./{gguf_filename}
PARAMETER temperature 1.0
PARAMETER top_p 0.95
PARAMETER num_ctx 2048
SYSTEM "{system_prompt}"
"""
        with open("/output/gguf/Modelfile", "w") as f:
            f.write(modelfile)
        print("Modelfile written.")

    # --- Test inference ---
    print("\n--- Test Inference ---")
    model.eval()

    test_messages = [{"role": "user", "content":
        "I'm a single mom with two kids ages 3 and 7. I just lost my job "
        "last week and I live in Hennepin County. What help is available?"}]

    inputs = tokenizer.apply_chat_template(
        test_messages, tokenize=True, add_generation_prompt=True, return_tensors="pt",
        return_dict=True,
    )
    input_ids = inputs["input_ids"].to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            input_ids=input_ids, max_new_tokens=512,
            temperature=1.0, top_p=0.95, do_sample=True,
        )
    response = tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)
    print(response[:500])

    # Commit volume
    output_vol.commit()

    # List outputs
    for root, dirs, files in os.walk("/output"):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path) / 1024 / 1024
            print(f"  {path} ({size:.1f} MB)")


@app.function(
    volumes={"/output": output_vol},
    timeout=30 * MINUTES,
)
def download_results():
    """List files in the output volume."""
    import os
    print("Files in output volume:")
    for root, dirs, files in os.walk("/output"):
        for f in files:
            path = os.path.join(root, f)
            size = os.path.getsize(path) / 1024 / 1024
            print(f"  {path} ({size:.1f} MB)")


@app.local_entrypoint()
def main():
    finetune.remote()
