# 参与

## 改什么

课程在 `data/curriculum/`，同形词和错误库在 `data/pitfalls/`。教学流程在 `SKILL.md`。命令行在 `src/oto/`。

N2、N1 目前只有路径，没有课文。要加内容就沿用现有 YAML：`id`、`level`、`prerequisites`、`reading`、`zh`。不要把空单元标成已经可教。

## 日语必须对

- 例句用日语语序，助词要在。
- 读音写假名。助词は、へ、を在注音里按发音写成わ、え、お，并在需要时说明。
- 音高是东京音的核位置：0 是平板。不确定就不要写 `accent`。
- 同形词要同时写日语里的意思和中文里的意思。

改完运行：

```bash
pip install -e ".[dev]"
pytest -q
```

发音相关的改动另装 `.[teach,praat]`，用真实音频跑 `oto analyze`，不要手写分数。

## 英文

Issues and lesson corrections are welcome in Chinese or English. Japanese examples need a kana reading and a Chinese gloss. Leave `accent` empty when the Tokyo pitch nucleus is uncertain.
