# Modal Project Claude Notes
Below are two sections that include information that Claude used in the project:<br>	
1. Excerpts from the project's `CLAUDE.md` file
2. Permissions allowed in the project's `.claude/settings.local.json` file

## `CLAUDE.md` Excerpts

These are all the notes that were included in the `CLAUDE.md` file for the project pertaining to Modal

### Modal Fine-Tuning (Cloud GPU)

```bash
modal run deploy/modal_finetune.py        # Unsloth QLoRA on A100 (preferred)
modal run deploy/modal_finetune_plain.py  # Raw PEFT QLoRA on A100 (fallback)
modal run deploy/modal_finetune_plain.py::convert_gguf  # Re-merge LoRA + GGUF export without retraining
modal volume get navigator-finetune-output /gguf/ ./output/gguf/  # Download GGUF to local
modal run deploy/modal_generate_training.py --workers 4              # Generate English (Gemini) + translate (Cloud Translate NMT)
modal run deploy/modal_generate_training.py --count 500 --workers 2  # Smaller run
modal run deploy/modal_generate_training.py --review-only            # Review/improve existing translations with Gemini
modal secret create gcloud-translate GOOGLE_CLOUD_PROJECT=<project-id> GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat service-account.json)"  # Cloud Translate auth
modal run deploy/modal_finetune_multilingual.py --lang all  # Fine-tune Hmong + Somali LoRA adapters
```

### Modal (Legacy — training only, not used for live demo)
Modal is used for cloud GPU training scripts (`deploy/modal_finetune*.py`, `deploy/modal_generate_training.py`) but NOT for the live demo. Gradio static files failed behind Modal's ASGI proxy. Key gotchas for training scripts:
- `modal.gpu` module removed in SDK 1.4.x — use `gpu="A100-80GB:4"` string format
- `output_vol.commit()` between phases; uncommitted writes lost on crash
- `modal secret create` for gemini-api, huggingface, gcloud-translate
- `.starmap()` for parallel GPU workers; each writes own file to avoid Volume conflicts
- `git+https://` pip installs require `.apt_install("git")`


## `.claude/settings.local.json` Excerpts

These are the specific permissions that were allowed in the project pertaining to Modal

- "Bash(modal profile:*)",
- "Bash(pkill -f \"modal serve\")",
- "Bash(modal run:*)",