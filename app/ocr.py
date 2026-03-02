"""Receipt OCR via DeepSeek-OCR-2. Returns raw text; parsing is in parser.py."""

import os
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import List

import torch
import fitz
from transformers import AutoModel, AutoTokenizer
from dotenv import load_dotenv

# Load .env file
load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME_OCR")

if not MODEL_NAME:
    raise RuntimeError("MODEL_NAME_OCR is not set")

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

_model = None
_tokenizer = None


def _load_model():
    global _model, _tokenizer
    if _model is not None:
        return
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module="transformers")
        _model = AutoModel.from_pretrained(
            MODEL_NAME,
            _attn_implementation="eager",
            trust_remote_code=True,
            use_safetensors=True,
            low_cpu_mem_usage=True,
            device_map="cuda:0",
            torch_dtype=torch.bfloat16,
        )
    _model = _model.eval()


def _pdf_to_images(pdf_path: str) -> List[str]:
    doc = fitz.open(pdf_path)
    paths: List[str] = []
    for page_idx in range(len(doc)):
        pix = doc[page_idx].get_pixmap(dpi=200)
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False, prefix=f"page{page_idx}_",
        )
        path = tmp.name
        tmp.close()
        pix.save(path)
        paths.append(path)
    doc.close()
    return paths


def _ocr_image(image_path: str) -> str:
    _load_model()
    prompt = "<image>\nFree OCR. "
    tmpdir = tempfile.mkdtemp()
    try:
        tmpdir_abs = str(Path(tmpdir).resolve())
        Path(tmpdir_abs).mkdir(parents=True, exist_ok=True)
        (Path(tmpdir_abs) / "images").mkdir(exist_ok=True)
        _model.infer(
            _tokenizer,
            prompt=prompt,
            image_file=image_path,
            output_path=tmpdir_abs,
            base_size=1024,
            image_size=768,
            crop_mode=True,
            save_results=True,
        )
        result_path = Path(tmpdir_abs) / "result.mmd"
        if result_path.exists():
            return result_path.read_text(encoding="utf-8").strip()
        return ""
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    ext = path.suffix.lower()

    if ext == ".pdf":
        tmp_imgs = _pdf_to_images(file_path)
        try:
            pages = [_ocr_image(img) for img in tmp_imgs]
            return "\n\n".join(pages)
        finally:
            for img in tmp_imgs:
                try:
                    os.unlink(img)
                except OSError:
                    pass

    if ext not in SUPPORTED_IMAGES:
        raise ValueError(
            f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_IMAGES | {'.pdf'}))}"
        )
    return _ocr_image(file_path)
