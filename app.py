from pathlib import Path
import uuid

from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

from omr import grade_answer_sheet, parse_answer_key

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _default_form_data() -> dict[str, str]:
    return {
        "answer_key": "",
        "num_questions": "80",
        "options": "4",
        "questions_per_row": "20",
        "allow_multiple": "on",
    }


def _render_index_error(error: str):
    form_data = _default_form_data()
    form_data.update(
        {
            "answer_key": request.form.get("answer_key", ""),
            "num_questions": request.form.get("num_questions", "80"),
            "options": request.form.get("options", "4"),
            "questions_per_row": request.form.get("questions_per_row", "20"),
            "allow_multiple": request.form.get("allow_multiple", ""),
        }
    )
    return render_template("index.html", error=error, form_data=form_data)


@app.route("/health", methods=["GET"])
def health() -> tuple[str, int]:
    return "ok", 200


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html", form_data=_default_form_data())

    file = request.files.get("answer_sheet")
    answer_key_text = request.form.get("answer_key", "")
    num_questions_raw = request.form.get("num_questions", "")
    options_raw = request.form.get("options", "")
    questions_per_row_raw = request.form.get("questions_per_row", "")
    allow_multiple = request.form.get("allow_multiple") == "on"

    if not file or file.filename == "":
        return _render_index_error("请先上传答题卡图片。")

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower() or ".jpg"
    if ext not in ALLOWED_EXTENSIONS:
        return _render_index_error("仅支持 jpg/jpeg/png/bmp/webp 图片格式。")

    try:
        num_questions = int(num_questions_raw)
        options = int(options_raw)
        questions_per_row = int(questions_per_row_raw)
        if num_questions <= 0 or not (2 <= options <= 8) or questions_per_row <= 0:
            raise ValueError
    except ValueError:
        return _render_index_error("题目数量>0、选项数在 2~8、每行题数>0。")

    try:
        answer_key = parse_answer_key(answer_key_text, num_questions, options)
    except ValueError as exc:
        return _render_index_error(str(exc))

    saved_name = f"{uuid.uuid4().hex}{ext}"
    image_path = UPLOAD_DIR / saved_name
    file.save(image_path)

    try:
        result = grade_answer_sheet(
            str(image_path),
            answer_key,
            options=options,
            questions_per_row=questions_per_row,
            allow_multiple=allow_multiple,
        )
    except Exception as exc:  # noqa: BLE001
        return _render_index_error(f"识别失败：{exc}")

    return render_template("result.html", result=result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
