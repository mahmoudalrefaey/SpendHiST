"""Receipt OCR engine — converts image/PDF files to raw text."""

import os
import shutil
import tempfile
import threading
import warnings
from pathlib import Path
from typing import List

import fitz
import torch
from transformers import AutoModel, AutoTokenizer

from app.config import MAX_PDF_PAGES, MODEL_NAME_OCR, OCR_DEVICE

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

# Prefer GPU device 0 when using CUDA (ops can override with CUDA_VISIBLE_DEVICES).
if OCR_DEVICE != "cpu":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

_model = None
_tokenizer = None
_infer_lock = threading.Lock()  # One in-flight infer at a time on shared weights.


def _use_cuda() -> bool:
    if OCR_DEVICE == "cpu":
        return False
    return torch.cuda.is_available()


def _load_model() -> None:
    global _model, _tokenizer
    if _model is not None:
        return
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME_OCR, trust_remote_code=True)
    use_cuda = _use_cuda()
    device_map = "cuda:0" if use_cuda else "cpu"
    dtype = torch.bfloat16 if use_cuda else torch.float32
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module="transformers")
        _model = AutoModel.from_pretrained(
            MODEL_NAME_OCR,
            _attn_implementation="eager",
            trust_remote_code=True,
            use_safetensors=True,
            low_cpu_mem_usage=True,
            device_map=device_map,
            torch_dtype=dtype,
        )
    _model = _model.eval()


def _pdf_to_images(pdf_path: str) -> List[str]:
    """Render PDF pages to temporary PNG files (capped by MAX_PDF_PAGES)."""
    doc = fitz.open(pdf_path)
    try:
        n = len(doc)
        if n > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF has {n} pages; maximum allowed is {MAX_PDF_PAGES}."
            )
        paths: List[str] = []
        for page_idx in range(n):
            pix = doc[page_idx].get_pixmap(dpi=200)
            tmp = tempfile.NamedTemporaryFile(
                suffix=".png",
                delete=False,
                prefix=f"page{page_idx}_",
            )
            path = tmp.name
            tmp.close()
            pix.save(path)
            paths.append(path)
        return paths
    finally:
        doc.close()


def _ocr_image(image_path: str) -> str:
    """Run OCR on a single image and return extracted text (thread-safe on shared model)."""
    _load_model()
    prompt = "<image>\nFree OCR. "
    tmpdir = tempfile.mkdtemp()
    try:
        tmpdir_abs = str(Path(tmpdir).resolve())
        Path(tmpdir_abs).mkdir(parents=True, exist_ok=True)
        (Path(tmpdir_abs) / "images").mkdir(exist_ok=True)
        with _infer_lock:
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
    """
    Extract text from an image or PDF file.
    PDFs are rendered page-by-page; pages are joined with blank lines.
    """
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
            f"Unsupported file type '{ext}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_IMAGES | {'.pdf'}))}"
        )

    return _ocr_image(file_path)
