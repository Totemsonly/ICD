from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid

from omr import grade_answer_sheet, parse_answer_key

app = Flask(__name__)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    file = request.files.get("answer_sheet")
    answer_key_text = request.form.get("answer_key", "")
    num_questions = request.form.get("num_questions", "")
    options = request.form.get("options", "")

    if not file or file.filename == "":
        return render_template("index.html", error="请先上传答题卡图片。")

    try:
        num_questions = int(num_questions)
        options = int(options)
        if num_questions <= 0 or options <= 1:
            raise ValueError
    except ValueError:
        return render_template("index.html", error="题目数量必须大于 0，选项数量必须大于 1。")

    try:
        answer_key = parse_answer_key(answer_key_text, num_questions, options)
    except ValueError as exc:
        return render_template("index.html", error=str(exc))

    ext = Path(secure_filename(file.filename)).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return render_template("index.html", error="仅支持 jpg/jpeg/png/bmp/webp 图片格式。")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename
    file.save(filepath)

    try:
        result = grade_answer_sheet(str(filepath), answer_key, options=options)
    except Exception as exc:  # noqa: BLE001
        return render_template("index.html", error=f"识别失败：{exc}")

    return render_template("result.html", result=result)


if __name__ == "__main__":
    app.run(debug=True)
