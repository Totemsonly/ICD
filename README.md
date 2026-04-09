# 基于 OpenCV 的客观题自动批改系统（长答题卡/多选题）

这是一个可直接运行的 Python Web 项目，针对你这种**长图答题卡**做了专门优化，支持：

- 上传长答题卡图片并自动评分；
- 单选 + 多选混合答案；
- 自定义题目数、选项数、每行题数（例如 20）；
- 输出逐题识别结果与告警信息。

## 功能特性

- ✅ Flask Web 界面：上传 + 配置 + 结果展示
- ✅ OpenCV 识别流程：透视矫正、二值化、分块识别
- ✅ 长卡布局识别：按“行 × 列（每行题数）”切分题块
- ✅ 多选题判分：答案支持 `A+C` / `A|C` / `AC`
- ✅ 识别质量告警：未识别过多时提示调整参数与拍摄条件

---

## 1. 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 启动项目

```bash
python app.py
```

访问：`http://127.0.0.1:5000`

健康检查：`http://127.0.0.1:5000/health`

---

## 3. 参数设置建议（针对长答题卡）

如果你的卡片与示例类似：

- 题目数量：`80`
- 每题选项数：`4`
- 每行题数：`20`
- 启用多选：勾选

> 当你发现大量“未识别”时，优先检查“每行题数”是否与版式一致。

---

## 4. 标准答案格式

- 单选：`A,B,C,D`
- 多选：`A+C,B,AC,D,A|C`

每题一项，题与题之间用逗号分隔，总数量必须等于题目数。

---

## 5. 识别流程（当前版本）

1. 检测答题卡外轮廓并尝试透视拉正；
2. 二值化得到填涂区域；
3. 按总题数和“每行题数”推导行列结构并切分题块；
4. 在每个题块内按选项方向（纵向）统计填涂率；
5. 按阈值判定单选/多选结果并与标准答案比对。

---

## 6. 项目结构

```text
.
├── app.py                # Flask 入口、参数校验
├── omr.py                # 长卡识别与评分核心逻辑
├── templates/
│   ├── index.html        # 上传与配置页面
│   └── result.html       # 批改结果页面
├── static/
│   └── style.css         # 样式
├── requirements.txt      # 依赖
└── package.sh            # 打包脚本
```

---

## 7. 打包下载

```bash
chmod +x package.sh
./package.sh
```

或按指定文件名打包（示例）：

```bash
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('.')
with zipfile.ZipFile('答题卡项目.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in root.rglob('*'):
        if any(part in {'.git', '.venv', 'uploads', '__pycache__'} for part in p.parts):
            continue
        if p.suffix == '.pyc' or p.name.endswith('.zip'):
            continue
        if p.is_file():
            zf.write(p, p.as_posix())
print('done')
PY
```

---

## 8. 落地建议

- 若后续固定某一类答题卡，建议加入模板定位点（角点/定位块）与版式参数文件；
- 可增加“识别调试图导出”（标注题块边界与选项填涂率）用于快速调参；
- 可将答案导入改为 CSV/Excel，提高批量阅卷效率。
