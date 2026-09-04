---
name: wrong-question-bank
description: Collects photographed wrong questions into a local bank and runs spaced-repetition practice. Use when the user mentions 错题, 错题本, 拍照收集错题, 题库, 错题练习, 复习错题, or attaches homework/exam photos to file or quiz.
---

# 错题本智能体

把用户拍的错题收入本地库，并按间隔复习抽题练习。题库与网页端共用同一文件。

先定位题库根目录（含 `bank.py`）：

1. 环境变量 `WRONG_QUESTION_BANK_DIR`
2. `%USERPROFILE%\WrongQuestionAgent` 或 `C:/Users/WY/WrongQuestionAgent`（哪个存在用哪个）
3. 当前工作区里若有 `bank.py` 且同目录有 `server.py`

数据：`<根目录>/data/bank.json`，图片：`<根目录>/data/images`。  
命令：`python "<根目录>/bank.py"`。不要把错题写入无关工程。

## 入库（拍照 / 贴图）

用户附上图片或给出本地图片路径时：

1. 看图（必要时结合用户补充）抽出结构化字段。一张图多题就拆成多条。
2. 把原图复制到 `data/images/`，文件名用新的 uuid + 原扩展名。
3. 写一份临时 JSON，再执行：

```bat
python "<根目录>/bank.py" add --file <临时json>
```

JSON 字段：

```json
{
  "subject": "数学",
  "source": "期中卷",
  "stem": "题目正文，不含解析",
  "options": ["A. ...", "B. ..."],
  "correctAnswer": "B",
  "userWrongAnswer": "C",
  "explanation": "正确做法与易错点",
  "knowledge": "知识点",
  "tags": ["填空", "易错"],
  "imageFile": "复制后的文件名，如 a1b2.jpg"
}
```

规则：

- 看不清就标 `[看不清]`，并请用户补一句，不要编造题面或答案。
- 用户没给正确答案时，`correctAnswer` 可空，解析写你能确定的部分。
- 入库后用一两句话确认：学科、题干摘要、是否已存图。
- 需要网页拍照时，让用户双击 `<根目录>/start.bat` 或运行 `python "<根目录>/server.py"`，打开 http://127.0.0.1:8765

## 练习

1. 运行：`python "<根目录>/bank.py" quiz -n 8`（可加 `--subject 数学`）。
2. 每次只出示题干、选项和图片路径；**先不要给正确答案和解析**。
3. 等用户作答后，对照 `correctAnswer` 判对错，再给解析。
4. 登记：`python "<根目录>/bank.py" review --id <id> --result correct|wrong`
5. 一组结束后用 `python "<根目录>/bank.py" stats` 汇报对错与到期数。

## 其它入口

- 统计 / 列表：`stats`、`list`、`list --due`
- 改某题：带原 `id` 再 `add --file`，不要无故覆盖复习字段
