# -*- coding: utf-8 -*-
"""错题库：读写、间隔复习、命令行。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_env_root = os.environ.get("WRONG_QUESTION_BANK_DIR", "").strip()
ROOT = Path(_env_root).expanduser().resolve() if _env_root else Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
INBOX_DIR = DATA_DIR / "inbox"
DEFAULT_NB = os.environ.get("WRONG_QUESTION_NOTEBOOK", "local")
NOTEBOOK_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")

ISO = "%Y-%m-%dT%H:%M:%S%z"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def validate_notebook(notebook_id: str) -> str:
    nb = (notebook_id or DEFAULT_NB).strip()
    if nb == "local":
        return "local"
    if not NOTEBOOK_RE.match(nb):
        raise ValueError("错题本编号无效")
    return nb


def notebook_root(notebook_id: str = DEFAULT_NB) -> Path:
    nb = validate_notebook(notebook_id)
    if nb == "local":
        return DATA_DIR
    return DATA_DIR / "notebooks" / nb


def bank_path(notebook_id: str = DEFAULT_NB) -> Path:
    return notebook_root(notebook_id) / "bank.json"


def image_dir(notebook_id: str = DEFAULT_NB) -> Path:
    return notebook_root(notebook_id) / "images"


def ensure_dirs(notebook_id: str = DEFAULT_NB) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    root = notebook_root(notebook_id)
    root.mkdir(parents=True, exist_ok=True)
    image_dir(notebook_id).mkdir(parents=True, exist_ok=True)


def create_notebook() -> str:
    nb = uuid.uuid4().hex[:16]
    ensure_dirs(nb)
    save_bank({"version": 1, "items": []}, notebook_id=nb)
    return nb


def load_bank(notebook_id: str = DEFAULT_NB) -> dict:
    ensure_dirs(notebook_id)
    path = bank_path(notebook_id)
    if not path.exists():
        return {"version": 1, "items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "items": []}


def save_bank(bank: dict, notebook_id: str = DEFAULT_NB) -> None:
    ensure_dirs(notebook_id)
    path = bank_path(notebook_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def empty_item() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "createdAt": iso(),
        "updatedAt": iso(),
        "subject": "",
        "source": "",
        "stem": "",
        "options": [],
        "correctAnswer": "",
        "userWrongAnswer": "",
        "explanation": "",
        "knowledge": "",
        "tags": [],
        "imageFile": "",
        "status": "active",
        "easiness": 2.5,
        "intervalDays": 0,
        "repetitions": 0,
        "nextReviewAt": iso(),
        "lastResult": "",
        "reviewCount": 0,
        "correctCount": 0,
        "wrongCount": 0,
    }


def merge_item(raw: dict) -> dict:
    item = empty_item()
    for key in item:
        if key in raw and raw[key] is not None:
            item[key] = raw[key]
    if raw.get("id"):
        item["id"] = str(raw["id"])
    item["options"] = [str(x) for x in (item.get("options") or []) if str(x).strip()]
    item["tags"] = [str(x).strip() for x in (item.get("tags") or []) if str(x).strip()]
    return item


def find_item(bank: dict, item_id: str) -> dict | None:
    for item in bank.get("items", []):
        if item.get("id") == item_id:
            return item
    return None


def upsert_item(payload: dict, notebook_id: str = DEFAULT_NB) -> dict:
    bank = load_bank(notebook_id)
    incoming = merge_item(payload)
    existing = find_item(bank, incoming["id"]) if payload.get("id") else None
    if existing:
        for key, value in incoming.items():
            if key in ("createdAt", "easiness", "intervalDays", "repetitions",
                       "nextReviewAt", "reviewCount", "correctCount", "wrongCount") and key not in payload:
                continue
            if key in payload:
                existing[key] = incoming[key]
        existing["updatedAt"] = iso()
        save_bank(bank, notebook_id)
        return existing
    bank.setdefault("items", []).append(incoming)
    save_bank(bank, notebook_id)
    return incoming


def delete_item(item_id: str, notebook_id: str = DEFAULT_NB) -> bool:
    bank = load_bank(notebook_id)
    before = len(bank.get("items", []))
    bank["items"] = [x for x in bank.get("items", []) if x.get("id") != item_id]
    if len(bank["items"]) == before:
        return False
    save_bank(bank, notebook_id)
    return True


def apply_review(item: dict, result: str) -> dict:
    """简化 SM-2：correct 拉长间隔，wrong 立刻重练。"""
    quality = 5 if result == "correct" else 1
    item["lastResult"] = result
    item["reviewCount"] = int(item.get("reviewCount") or 0) + 1
    item["updatedAt"] = iso()
    if result == "correct":
        item["correctCount"] = int(item.get("correctCount") or 0) + 1
    else:
        item["wrongCount"] = int(item.get("wrongCount") or 0) + 1

    easiness = float(item.get("easiness") or 2.5)
    easiness = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    easiness = max(1.3, easiness)
    item["easiness"] = round(easiness, 2)

    if result != "correct":
        item["repetitions"] = 0
        item["intervalDays"] = 0
        item["nextReviewAt"] = iso()
    else:
        reps = int(item.get("repetitions") or 0) + 1
        item["repetitions"] = reps
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 3
        else:
            interval = max(1, round(float(item.get("intervalDays") or 1) * easiness))
        item["intervalDays"] = interval
        item["nextReviewAt"] = iso(now_utc() + timedelta(days=interval))
    return item


def review_item(item_id: str, result: str, notebook_id: str = DEFAULT_NB) -> dict | None:
    if result not in ("correct", "wrong"):
        raise ValueError("result 必须是 correct 或 wrong")
    bank = load_bank(notebook_id)
    item = find_item(bank, item_id)
    if not item:
        return None
    apply_review(item, result)
    save_bank(bank, notebook_id)
    return item


def is_due(item: dict, at: datetime | None = None) -> bool:
    at = at or now_utc()
    nxt = parse_iso(item.get("nextReviewAt"))
    if nxt is None:
        return True
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt <= at


def quiz_items(n: int = 8, subject: str = "", notebook_id: str = DEFAULT_NB) -> list[dict]:
    bank = load_bank(notebook_id)
    items = [x for x in bank.get("items", []) if x.get("status", "active") != "archived"]
    if subject:
        items = [x for x in items if (x.get("subject") or "") == subject]
    due = [x for x in items if is_due(x)]
    due.sort(key=lambda x: parse_iso(x.get("nextReviewAt")) or now_utc())
    rest = [x for x in items if x not in due]
    rest.sort(key=lambda x: int(x.get("wrongCount") or 0), reverse=True)
    picked = (due + rest)[: max(1, n)]
    return picked


def stats(bank: dict | None = None, notebook_id: str = DEFAULT_NB) -> dict:
    bank = bank or load_bank(notebook_id)
    items = [x for x in bank.get("items", []) if x.get("status", "active") != "archived"]
    due = sum(1 for x in items if is_due(x))
    subjects = {}
    for x in items:
        key = x.get("subject") or "未分类"
        subjects[key] = subjects.get(key, 0) + 1
    return {
        "total": len(items),
        "due": due,
        "subjects": subjects,
    }


def public_quiz(item: dict) -> dict:
    """练习时先不把正确答案和解析发给前端展示逻辑以外的字段仍返回，前端自行隐藏。"""
    return item


def cmd_add(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    item = upsert_item(payload)
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    bank = load_bank()
    items = bank.get("items", [])
    if args.due:
        items = [x for x in items if is_due(x)]
    if args.subject:
        items = [x for x in items if x.get("subject") == args.subject]
    print(json.dumps({"stats": stats(bank), "items": items}, ensure_ascii=False, indent=2))
    return 0


def cmd_quiz(args: argparse.Namespace) -> int:
    items = quiz_items(n=args.n, subject=args.subject or "")
    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    item = review_item(args.id, args.result)
    if not item:
        print("未找到该错题", file=sys.stderr)
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="错题库命令行")
    sub = p.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="从 JSON 文件新增或更新")
    add_p.add_argument("--file", required=True)
    add_p.set_defaults(func=cmd_add)

    list_p = sub.add_parser("list", help="列出错题")
    list_p.add_argument("--due", action="store_true")
    list_p.add_argument("--subject", default="")
    list_p.set_defaults(func=cmd_list)

    quiz_p = sub.add_parser("quiz", help="抽取练习题")
    quiz_p.add_argument("-n", type=int, default=8)
    quiz_p.add_argument("--subject", default="")
    quiz_p.set_defaults(func=cmd_quiz)

    review_p = sub.add_parser("review", help="提交练习结果")
    review_p.add_argument("--id", required=True)
    review_p.add_argument("--result", required=True, choices=("correct", "wrong"))
    review_p.set_defaults(func=cmd_review)

    stats_p = sub.add_parser("stats", help="统计")
    stats_p.set_defaults(func=cmd_stats)
    return p


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
