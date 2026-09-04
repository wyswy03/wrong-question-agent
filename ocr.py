# -*- coding: utf-8 -*-
"""腾讯云 OCR：把错题照片转成文字。"""
from __future__ import annotations

import os
import re


def configured() -> bool:
    return bool(os.environ.get("TENCENTCLOUD_SECRET_ID") and os.environ.get("TENCENTCLOUD_SECRET_KEY"))


def _client():
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.ocr.v20181119 import ocr_client

    cred = credential.Credential(
        os.environ["TENCENTCLOUD_SECRET_ID"].strip(),
        os.environ["TENCENTCLOUD_SECRET_KEY"].strip(),
    )
    http_profile = HttpProfile()
    http_profile.endpoint = "ocr.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = http_profile
    region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou").strip() or "ap-guangzhou"
    return ocr_client.OcrClient(cred, region, profile)


def _lines_from_resp(resp) -> list[str]:
    detections = getattr(resp, "TextDetections", None) or []
    lines = []
    for item in detections:
        text = (getattr(item, "DetectedText", None) or "").strip()
        if text:
            lines.append(text)
    return lines


def _recognize_with(action: str, image_b64: str) -> list[str]:
    from tencentcloud.ocr.v20181119 import models

    client = _client()
    req = getattr(models, action + "Request")()
    req.ImageBase64 = image_b64
    resp = getattr(client, action)(req)
    return _lines_from_resp(resp)


def glue_short_lines(lines):
    glued = []
    buf = []
    for line in lines or []:
        t = (line or "").strip()
        if not t:
            continue
        if len(t) <= 2:
            buf.append(t)
            continue
        if buf:
            glued.append("".join(buf))
            buf = []
        glued.append(t)
    if buf:
        glued.append("".join(buf))
    return glued


def as_paragraph(text):
    raw = (text or "").replace("\r\n", "\n").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return ""
    short = sum(1 for ln in lines if len(ln) <= 2)
    joined = "".join(lines) if (len(lines) >= 4 and short >= len(lines) * 0.45) else " ".join(lines)
    return re.sub(r"\s+", " ", joined).strip()


def question_only(text):
    s = (text or '').strip()
    s = re.sub(r'\$\$[\s\S]*?\$\$', ' ', s)
    s = re.sub(r'\$[^$]*\$', ' ', s)
    s = re.split(r'\sX\s|×|✘|→|->', s, maxsplit=1)[0]
    s = re.split(r'应为|正确答案|正确\s*[:：]|因数拆错|配方公式|用错', s, maxsplit=1)[0]
    s = re.sub(r'\s+', ' ', s).strip()
    m = re.match(r'(\d+\s*[.、．]\s*.{0,120}?=\s*0)', s)
    if m:
        s = m.group(1).strip()
    return s


def parse_fields(lines: list[str]) -> dict:
    lines = glue_short_lines(lines)
    text = "\n".join(lines)
    stem = question_only(text) or text.strip()
    correct = ""
    wrong = ""
    explanation = ""
    subject = ""
    if re.search(r"数学|二次|方程|函数|三角", text):
        subject = "数学"
    elif re.search(r"英语|English", text, re.I):
        subject = "英语"
    elif re.search(r"物理", text):
        subject = "物理"
    for line in lines:
        m = re.search(r"(?:应为|正确答案|正确)\s*[:：]?\s*(.+)$", line)
        if m and not correct:
            correct = m.group(1).strip()
        if "配方" in line or "用错" in line or "解析" in line or "顶点" in line:
            explanation = (explanation + " " + line).strip()
        if re.search(r"顶点\s*\(", line) and "应为" not in line and not wrong:
            wrong = line
    return {
        "stem": stem,
        "subject": subject,
        "correctAnswer": correct,
        "userWrongAnswer": wrong,
        "explanation": as_paragraph(explanation),
        "text": text,
    }


def recognize_image_b64(image_b64: str) -> dict:
    if not configured():
        raise RuntimeError("未配置腾讯云 OCR 密钥")
    image_b64 = image_b64.strip()
    if not image_b64:
        raise ValueError("图片为空")
    last_error = None
    for action in ("GeneralAccurateOCR", "GeneralHandwritingOCR", "GeneralBasicOCR"):
        try:
            lines = _recognize_with(action, image_b64)
            if lines:
                fields = parse_fields(lines)
                fields["engine"] = action
                return fields
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return parse_fields([])
