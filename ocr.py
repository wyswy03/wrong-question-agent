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


def parse_fields(lines: list[str]) -> dict:
    text = "\n".join(lines)
    stem = text.strip()
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
        if "配方" in line or "用错" in line or "解析" in line:
            explanation = (explanation + " " + line).strip()
        if re.search(r"顶点\s*\(", line) and "应为" not in line and not wrong:
            wrong = line
    return {
        "stem": stem,
        "subject": subject,
        "correctAnswer": correct,
        "userWrongAnswer": wrong,
        "explanation": explanation,
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
