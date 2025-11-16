# veritas/core/sanitize.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re

# ざっくり安全なマスク
RE_EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
RE_PHONE = re.compile(r'(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?){2,3}\d{3,4}')
RE_ZIP   = re.compile(r'\b\d{3}-?\d{4}\b')
# 都道府県〜丁目・番地・号あたりを緩く拾う
RE_ADDR  = re.compile(r'(東京都|道|府|県|市|区|町|村).{0,40}?(丁目|番地|号|\d-\d|\d丁目)')
# “山田太郎/ヤマダタロウ/佐藤/鈴木” 等を簡易に（過検出を避けたいので控えめ）
RE_NAME  = re.compile(r'([一-龥]{2,4}|[ァ-ン]{3,10})\s?(さん|様)?')

def _mask(m: re.Match, token: str) -> str:
    return f'〔{token}〕'

def mask_pii(text: str) -> str:
    s = text or ""
    s = RE_EMAIL.sub(lambda m: _mask(m, "メール"), s)
    s = RE_PHONE.sub(lambda m: _mask(m, "電話"), s)
    s = RE_ZIP.sub(lambda m: _mask(m, "郵便番号"), s)
    s = RE_ADDR.sub(lambda m: _mask(m, "住所"), s)
    # 名前は最後に（住所等に含まれる名詞を過剰マスクしないため）
    s = RE_NAME.sub(lambda m: _mask(m, "個人名"), s)
    return s
