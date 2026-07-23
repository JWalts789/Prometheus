"""QLoRA finetuning + in-process inference for the model that GROWS.

4-bit NF4 base (bitsandbytes) + a LoRA adapter (peft), trained with a plain HF Trainer
(no trl — avoids API churn). SFT masking: loss is computed only on the response tokens.
`make_generator()` loads base+adapter and returns a `generate(prompt)->str` for eval.

Sized for a 4GB laptop GPU on a 0.5-1.5B base. Falls back to CPU if CUDA is absent.
"""
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel

SYSTEM = "You are a concise assistant. Answer in as few words as possible."
_QWEN_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def _bnb_config():
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )


def _load_tokenizer(base_model):
    tok = AutoTokenizer.from_pretrained(base_model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


def _load_base(base_model, four_bit=True):
    kw = {}
    if four_bit and torch.cuda.is_available():
        kw = dict(quantization_config=_bnb_config(), device_map="cuda")
    else:
        kw = dict(torch_dtype=torch.float32, device_map=("cuda" if torch.cuda.is_available() else "cpu"))
    model = AutoModelForCausalLM.from_pretrained(base_model, **kw)
    return model


def _encode(tokenizer, ex, max_len):
    """ex = {'prompt': str, 'response': str} -> input_ids/labels with prompt masked."""
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ex["prompt"]}]
    prompt_text = tokenizer.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    resp_ids = tokenizer(ex["response"], add_special_tokens=False)["input_ids"] + [tokenizer.eos_token_id]
    input_ids = (prompt_ids + resp_ids)[:max_len]
    labels = ([-100] * len(prompt_ids) + resp_ids)[:max_len]
    return {"input_ids": input_ids, "labels": labels}


class _Collator:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, batch):
        maxlen = max(len(b["input_ids"]) for b in batch)
        input_ids, labels, attn = [], [], []
        for b in batch:
            n = maxlen - len(b["input_ids"])
            input_ids.append(b["input_ids"] + [self.pad_id] * n)
            labels.append(b["labels"] + [-100] * n)
            attn.append([1] * len(b["input_ids"]) + [0] * n)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "attention_mask": torch.tensor(attn, dtype=torch.long),
        }


def train_qlora(base_model, examples, out_dir, epochs=3, lr=2e-4, max_len=512,
                r=16, alpha=32, batch_size=1, grad_accum=8, four_bit=True,
                resume_adapter=None):
    """Train a LoRA adapter on `examples` (list of {'prompt','response'}); save to out_dir.

    If `resume_adapter` is given, CONTINUE training that adapter (continual learning —
    the organism's brain keeps evolving) instead of starting a fresh LoRA from the base.
    """
    tok = _load_tokenizer(base_model)
    model = _load_base(base_model, four_bit=four_bit)
    if four_bit and torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False

    if resume_adapter:
        model = PeftModel.from_pretrained(model, str(resume_adapter), is_trainable=True)
        print(f"[qlora] continuing from adapter: {resume_adapter}")
    else:
        lora = LoraConfig(r=r, lora_alpha=alpha, lora_dropout=0.05, bias="none",
                          task_type="CAUSAL_LM", target_modules=_QWEN_TARGETS)
        model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    data = [_encode(tok, ex, max_len) for ex in examples]
    args = TrainingArguments(
        output_dir=str(out_dir) + "_hf",
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        num_train_epochs=epochs,
        learning_rate=lr,
        fp16=torch.cuda.is_available(),
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        optim=("paged_adamw_8bit" if (four_bit and torch.cuda.is_available()) else "adamw_torch"),
        gradient_checkpointing=torch.cuda.is_available(),
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    trainer = Trainer(model=model, args=args, train_dataset=data, data_collator=_Collator(tok.pad_token_id))
    trainer.train()
    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))
    return out_dir


def make_generator(base_model, adapter_dir=None, four_bit=True, max_new_tokens=40):
    """Return generate(prompt)->str for base (adapter_dir=None) or base+adapter."""
    tok = _load_tokenizer(base_model)
    model = _load_base(base_model, four_bit=four_bit)
    if adapter_dir is not None:
        model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()

    def generate(prompt):
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        prompt_text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        enc = tok(prompt_text, add_special_tokens=False, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)

    return generate


if __name__ == "__main__":
    # VRAM smoke test: does QLoRA of the base fit + run on this 4GB GPU?
    import time
    from config import BASE_MODEL, MODELS_DIR

    print("CUDA:", torch.cuda.is_available(),
          "| device:", (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"))
    demo = [
        {"prompt": "What is the capital of the Ashfell?", "response": "Cinderhold."},
        {"prompt": "How many wings does the Cindermoth have?", "response": "Six."},
    ] * 5  # 10 tiny examples

    t0 = time.time()
    out = MODELS_DIR / "_smoke_adapter"
    train_qlora(BASE_MODEL, demo, out, epochs=3, max_len=128)
    print(f"[smoke] trained in {time.time()-t0:.1f}s -> {out}")
    if torch.cuda.is_available():
        print(f"[smoke] peak VRAM: {torch.cuda.max_memory_allocated()/1e9:.2f} GB")

    gen = make_generator(BASE_MODEL, adapter_dir=out)
    print("[smoke] Q: capital of the Ashfell? ->", gen("What is the capital of the Ashfell?").strip())
