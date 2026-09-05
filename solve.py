# -*- coding: utf-8 -*-
"""根据题干生成答案和解析（腾讯混元 / 兼容接口）。"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


def configured() -> bool:
    if os.environ.get("HUNYUAN_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
        return True
    return bool(os.environ.get("TENCENTCLOUD_SECRET_ID") and os.environ.get("TENCENTCLOUD_SECRET_KEY"))


def _strip_fence(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _parse_json(text: str) -> dict:
    s = _strip_fence(text)
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"explanation": s, "correctAnswer": ""}


def _prompt(stem: str, ocr_text: str) -> str:
    body = (stem or "").strip() or (ocr_text or "").strip()
    extra = ""
    if ocr_text and stem and ocr_text.strip() != stem.strip():
        extra = "\nOCR原文（可能含手写过程，仅供参考）：\n%s" % ocr_text[:1500]
    return (
        "你是中小学教师。根据题目写出正确答案和简明解析。"
        "即使原图不是错题、没有批改，也要正常作答。"
        "只输出一个 JSON 对象，不要其它文字。字段："
        '{"subject":"学科","stem":"清洗后的题目（不要解答过程）",'
        '"correctAnswer":"最终答案","knowledge":"知识点",'
        '"explanation":"分步解析，用连贯中文，不要一字一行"}。\n'
        "题目：\n%s%s" % (body, extra)
    )


def _chat_openai_compat(prompt: str) -> str:
    key = (os.environ.get("HUNYUAN_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if os.environ.get("HUNYUAN_API_KEY"):
        base = os.environ.get("SOLVE_API_BASE", "https://api.hunyuan.cloud.tencent.com/v1").rstrip("/")
        model = os.environ.get("SOLVE_MODEL", "hunyuan-lite")
    else:
        base = os.environ.get("SOLVE_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
        model = os.environ.get("SOLVE_MODEL", "deepseek-chat")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""


def _chat_hunyuan_sdk(prompt: str) -> str:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.hunyuan.v20230901 import hunyuan_client, models

    cred = credential.Credential(
        os.environ["TENCENTCLOUD_SECRET_ID"].strip(),
        os.environ["TENCENTCLOUD_SECRET_KEY"].strip(),
    )
    http_profile = HttpProfile()
    http_profile.endpoint = "hunyuan.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = http_profile
    region = os.environ.get("TENCENTCLOUD_REGION", "ap-guangzhou").strip() or "ap-guangzhou"
    client = hunyuan_client.HunyuanClient(cred, region, profile)
    req = models.ChatCompletionsRequest()
    req.Model = os.environ.get("SOLVE_MODEL", "hunyuan-lite")
    msg = models.Message()
    msg.Role = "user"
    msg.Content = prompt
    req.Messages = [msg]
    req.Stream = False
    resp = client.ChatCompletions(req)
    choices = getattr(resp, "Choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "Message", None)
    return (getattr(message, "Content", None) or "").strip()


def explain_question(stem: str, ocr_text: str = "") -> dict:
    if not configured():
        return {}
    prompt = _prompt(stem, ocr_text)
    last_error = None
    text = ""
    if os.environ.get("HUNYUAN_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"):
        try:
            text = _chat_openai_compat(prompt)
        except Exception as exc:
            last_error = exc
    if not text and os.environ.get("TENCENTCLOUD_SECRET_ID"):
        try:
            text = _chat_hunyuan_sdk(prompt)
        except Exception as exc:
            last_error = exc
    if not text:
        if last_error:
            raise last_error
        return {}
    data = _parse_json(text)
    return {
        "subject": str(data.get("subject") or "").strip(),
        "stem": str(data.get("stem") or "").strip(),
        "correctAnswer": str(data.get("correctAnswer") or "").strip(),
        "knowledge": str(data.get("knowledge") or "").strip(),
        "explanation": str(data.get("explanation") or "").strip(),
    }
