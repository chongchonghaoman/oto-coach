"""Command line for Oto. Human text is Chinese. ``--json`` is for agents."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from oto import __version__
from oto.anki import iter_cards, write_apkg, write_csv
from oto.curriculum import coverage, load_curriculum, validate
from oto.learner import (
    due_cards,
    fresh_state,
    grade,
    load_state,
    log_mistake,
    refresh_completed,
    save_state,
)
from oto.lesson import render_lesson
from oto.paths import learner_path
from oto.pitfalls import load_pitfalls
from oto.placement import apply_placement, load_questions, parse_submit, render_questions, score_answers
from oto.planner import commit_new_items, plan_session
from oto.quiz import build_quiz, render_quiz


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oto", description="音 Oto：给中文母语者的日语学习工具。")
    parser.add_argument("--version", action="version", version=f"oto {__version__}")
    parser.add_argument("--learner", help="学习者档案路径。默认 ~/.oto/learner.yaml")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    parser.add_argument("--date", help="当作今天，YYYY-MM-DD。测试和补课用。")
    sub = parser.add_subparsers(dest="command")

    stats = sub.add_parser("stats", help="课程规模与校验")
    stats.set_defaults(func=_cmd_stats)

    setup = sub.add_parser("setup", help="检查发音和词典后端")
    setup.set_defaults(func=_cmd_setup)

    place = sub.add_parser("place", help="分班测验")
    place.add_argument("--submit", help="答案，如 k1=a,n5a=b")
    place.set_defaults(func=_cmd_place)

    plan = sub.add_parser("plan", help="按时间安排今天的一步")
    plan.add_argument("--minutes", type=int)
    plan.add_argument("--unit")
    plan.add_argument("--force", action="store_true")
    plan.set_defaults(func=_cmd_plan)

    lesson = sub.add_parser("lesson", help="打印一节课")
    lesson.add_argument("--minutes", type=int)
    lesson.add_argument("--unit")
    lesson.add_argument("--force", action="store_true")
    lesson.add_argument("--commit", action="store_true", help="把这节新词写进档案")
    lesson.set_defaults(func=_cmd_lesson)

    review = sub.add_parser("review", help="到期的复习")
    review.add_argument("--minutes", type=int, default=15)
    review.set_defaults(func=_cmd_review)

    quiz = sub.add_parser("quiz", help="小测")
    quiz.add_argument("--unit")
    quiz.add_argument("--level")
    quiz.add_argument("--n", type=int, default=5)
    quiz.add_argument("--seed", type=int, default=0)
    quiz.add_argument("--reveal", action="store_true")
    quiz.set_defaults(func=_cmd_quiz)

    grade_cmd = sub.add_parser("grade", help="给一张卡片打分")
    grade_cmd.add_argument("item")
    grade_cmd.add_argument("--rating", required=True, choices=["again", "hard", "good", "easy"])
    grade_cmd.set_defaults(func=_cmd_grade)

    mistake = sub.add_parser("mistake", help="记下一次错误")
    mistake.add_argument("--error", required=True)
    mistake.add_argument("--item")
    mistake.add_argument("--detail", default="")
    mistake.set_defaults(func=_cmd_mistake)

    lookup = sub.add_parser("lookup", help="查词、同形词、字形")
    lookup.add_argument("text")
    lookup.add_argument("--jmdict", action="store_true")
    lookup.set_defaults(func=_cmd_lookup)

    reference = sub.add_parser("reference", help="读音和东京重音")
    reference.add_argument("text")
    reference.add_argument("--reading")
    reference.add_argument("--accent", type=int)
    reference.set_defaults(func=_cmd_reference)

    speak = sub.add_parser("speak", help="合成参考音")
    speak.add_argument("text")
    speak.add_argument("-o", "--output", required=True)
    speak.add_argument("--engine", default="auto", choices=["auto", "openjtalk", "voicevox"])
    speak.add_argument("--accent", type=int)
    speak.set_defaults(func=_cmd_speak)

    analyze = sub.add_parser("analyze", help="分析一段朗读")
    analyze.add_argument("audio")
    analyze.add_argument("--text", required=True)
    analyze.add_argument("--reading")
    analyze.add_argument("--accent", type=int)
    analyze.add_argument("--chart")
    analyze.add_argument("--no-hatsuon", action="store_true")
    analyze.add_argument("--transcribe", action="store_true")
    analyze.set_defaults(func=_cmd_analyze)

    pitch = sub.add_parser("pitch", help="合成若干词并画出各自的 F0")
    pitch.add_argument("words", nargs="+")
    pitch.add_argument("-o", "--output", required=True)
    pitch.add_argument("--engine", default="openjtalk", choices=["auto", "openjtalk", "voicevox"])
    pitch.add_argument("--particle", default="", help="合成时附在词后，例如 が。图用带助词的高低型。")
    pitch.set_defaults(func=_cmd_pitch)

    export = sub.add_parser("export", help="导出 Anki")
    export.add_argument("kind", choices=["anki"])
    export.add_argument("-o", "--output", required=True)
    export.add_argument("--format", choices=["csv", "apkg"], default="csv")
    export.add_argument("--all", action="store_true", help="导出全部课程，不只已学")
    export.set_defaults(func=_cmd_export)

    return parser


def _today(args: argparse.Namespace) -> date:
    if args.date:
        return date.fromisoformat(args.date)
    return date.today()


def _state_path(args: argparse.Namespace) -> Path:
    return learner_path(args.learner)


def _emit(args: argparse.Namespace, payload: Any, text: str | None = None) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif text is not None:
        print(text, end="" if text.endswith("\n") else "\n")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    errors = validate(curriculum)
    counts = coverage(curriculum)
    counts["false_friends"] = len(pitfalls["false_friends"])
    counts["errors"] = len(pitfalls["errors"])
    counts["correspondences"] = len(pitfalls["correspondences"])
    counts["shinjitai"] = len(pitfalls["shinjitai"])
    counts["cognates"] = len(pitfalls["cognates"])
    payload = {"ok": not errors, "counts": counts, "errors": errors}
    if errors and not args.json:
        print("课程校验失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    lines = ["课程规模"]
    for key, value in counts.items():
        lines.append(f"  {key}: {value}")
    if not errors:
        lines.append("校验通过。")
    return _emit(args, payload, "\n".join(lines) + "\n")


def _cmd_setup(args: argparse.Namespace) -> int:
    from oto.pronounce.status import backend_status

    status = backend_status()
    lines = ["后端"]
    for key, value in status.items():
        if key == "licenses_zh":
            continue
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("授权与边界")
    lines.extend(f"  - {line}" for line in status["licenses_zh"])
    lines.append("")
    lines.append("可选安装")
    lines.append("  pip install 'oto-coach[teach]'     # OpenJTalk、波形、图")
    lines.append("  pip install 'oto-coach[praat]'     # Parselmouth，GPL-3.0")
    lines.append("  pip install 'oto-coach[score]'     # hatsuon 运行时：librosa、onnxruntime")
    lines.append("  pip install 'hatsuon[export]' && hatsuon-export")
    lines.append("  VOICEVOX CPU：download-linux-x64 --models-pattern 0.vvm，目录给 OTO_VOICEVOX_DIR")
    lines.append("  pip install 'oto-coach[asr]'       # faster-whisper int8，Kotoba-Whisper")
    lines.append("  pip install 'oto-coach[dict]'      # JMdict，CC BY-SA，数据不进仓库")
    lines.append("  pip install 'oto-coach[anki]'      # genanki，导出 apkg")
    return _emit(args, status, "\n".join(lines) + "\n")


def _cmd_place(args: argparse.Namespace) -> int:
    questions = load_questions()
    if not args.submit:
        payload = {
            "questions": [
                {
                    "id": q["id"],
                    "section": q["section"],
                    "prompt_zh": q["prompt_zh"],
                    "choices": q["choices"],
                }
                for q in questions
            ]
        }
        return _emit(args, payload, render_questions(questions))
    result = score_answers(questions, parse_submit(args.submit))
    path = _state_path(args)
    state = load_state(path)
    apply_placement(state, result, load_curriculum())
    save_state(path, state)
    result["learner"] = str(path)
    text = result["summary_zh"] + f"\n级别：{result['level']}\n档案：{path}\n"
    if any(not row["ok"] for row in result["detail"]):
        text += "\n错了的题\n"
        for row in result["detail"]:
            if not row["ok"]:
                text += f"- {row['id']}：{row['explain_zh']}\n"
    return _emit(args, result, text)


def _plan(args: argparse.Namespace) -> tuple[dict, dict, dict, Path]:
    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    path = _state_path(args)
    state = load_state(path)
    refresh_completed(state, curriculum["units"])
    plan = plan_session(
        curriculum,
        state,
        minutes=args.minutes,
        today=_today(args),
        unit_id=getattr(args, "unit", None),
        force=getattr(args, "force", False),
        pitfalls=pitfalls,
    )
    return plan, state, curriculum, path


def _cmd_plan(args: argparse.Namespace) -> int:
    plan, _state, _curriculum, path = _plan(args)
    plan = _jsonable_plan(plan)
    plan["learner"] = str(path)
    return _emit(args, plan, render_lesson(plan, load_pitfalls()))


def _cmd_lesson(args: argparse.Namespace) -> int:
    plan, state, curriculum, path = _plan(args)
    committed: list[str] = []
    if args.commit:
        if plan["kind"] != "lesson":
            raise ValueError("现在没有可写入的新课。")
        committed = commit_new_items(state, plan, curriculum)
        save_state(path, state)
    payload = _jsonable_plan(plan)
    payload["learner"] = str(path)
    payload["committed"] = committed
    text = render_lesson(plan, load_pitfalls())
    if committed:
        text += "\n已写入：" + "、".join(committed) + f"\n档案：{path}\n"
    return _emit(args, payload, text)


def _cmd_review(args: argparse.Namespace) -> int:
    from oto.lesson import key_for, prompt_for

    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    path = _state_path(args)
    state = load_state(path)
    today = _today(args)
    cards = due_cards(state, today)
    items = {}
    for unit in curriculum["units"]:
        for item in unit.get("items") or []:
            items[item["id"]] = item
    rows = []
    for card in cards:
        item = items.get(card["item_id"])
        if not item:
            continue
        rows.append(
            {
                "id": card["item_id"],
                "due": card.get("due"),
                "reps": card.get("reps"),
                "prompt": prompt_for(item),
                "key": key_for(item, pitfalls),
            }
        )
    shown = rows[: max(1, int(args.minutes * 60 / 25))] if rows else []
    payload = {"date": today.isoformat(), "due": len(rows), "items": shown, "learner": str(path)}
    lines = [f"复习 · {today.isoformat()} · 到期 {len(rows)}", ""]
    if not shown:
        lines.append("没有到期的卡片。新学的内容从第二天开始出现。")
    else:
        lines.append("先做")
        for index, row in enumerate(shown, start=1):
            lines.append(f"{index}. ({row['id']}) {row['prompt']}")
        lines.append("")
        lines.append("———— 对照 ————")
        for index, row in enumerate(shown, start=1):
            lines.append(f"{index}. {row['key']}")
    return _emit(args, payload, "\n".join(lines) + "\n")


def _cmd_quiz(args: argparse.Namespace) -> int:
    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    quiz = build_quiz(
        curriculum,
        unit_id=args.unit,
        level=args.level,
        n=args.n,
        seed=args.seed,
        pitfalls=pitfalls,
    )
    if args.json and not args.reveal:
        public = {"n": quiz["n"], "prompts": quiz["prompts"]}
        return _emit(args, public)
    return _emit(args, quiz, render_quiz(quiz, reveal=args.reveal or args.json))


def _cmd_grade(args: argparse.Namespace) -> int:
    path = _state_path(args)
    state = load_state(path)
    if not any(item["id"] == args.item for unit in load_curriculum()["units"] for item in unit.get("items") or []):
        raise ValueError(f"没有这个条目：{args.item}")
    card = grade(state, args.item, args.rating, _today(args))
    refresh_completed(state, load_curriculum()["units"])
    save_state(path, state)
    text = f"{args.item} → {args.rating}。下次：{card['due']}。间隔 {card['interval']} 天。\n"
    return _emit(args, {"learner": str(path), "card": card}, text)


def _cmd_mistake(args: argparse.Namespace) -> int:
    path = _state_path(args)
    state = load_state(path)
    entry = log_mistake(
        state,
        error_id=args.error,
        item_id=args.item,
        detail=args.detail,
        today=_today(args),
    )
    save_state(path, state)
    return _emit(args, {"learner": str(path), "mistake": entry}, f"已记下 {args.error}。\n")


def _cmd_lookup(args: argparse.Namespace) -> int:
    from oto.lookup import furigana, lookup_jmdict, lookup_local

    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    local = lookup_local(args.text, curriculum, pitfalls)
    local["furigana"] = furigana(args.text)
    local["jmdict"] = lookup_jmdict(args.text)
    lines = [f"查 {args.text}", ""]
    if local["false_friends"]:
        lines.append("同形词")
        for trap in local["false_friends"]:
            lines.append(f"- {trap['jp']}：日语 {trap['ja_zh']}；中文常作 {trap['zh_zh']}。{trap.get('trap_zh', '')}")
    if local["cognates"]:
        lines.append("可借用")
        for entry in local["cognates"]:
            lines.append(f"- {entry['jp']}：{entry['zh']}。{entry.get('note_zh', '')}")
    if local["script"]:
        lines.append("字形")
        for note in local["script"]:
            lines.append(f"- {note['jp']} / 繁 {note.get('trad', '—')} / 简 {note.get('simp', '—')}。{note.get('note_zh', '')}")
    if local["correspondences"]:
        lines.append("音读线索（是倾向，不是定律）")
        for rule in local["correspondences"]:
            lines.append(f"- {rule['title_zh']}：{rule['summary_zh']}")
    if local["curriculum"]:
        lines.append("课文")
        for hit in local["curriculum"]:
            lines.append(f"- {hit['jp']} {hit.get('reading') or ''} {hit.get('zh') or ''} {hit.get('pattern') or ''}")
    jmdict = local.get("jmdict") or {}
    if jmdict.get("available"):
        lines.append(f"JMdict（{jmdict['license']}）")
        lines.append(jmdict["attribution"])
        for entry in jmdict["entries"]:
            lines.append(f"- {entry}")
        if not jmdict["entries"]:
            lines.append("- （没有条目）")
    elif args.jmdict:
        lines.append(f"JMdict 未用：{jmdict.get('reason')}")
    furigana_info = local["furigana"]
    if furigana_info.get("available"):
        lines.append(f"引擎读音 {furigana_info.get('read')} / 发音 {furigana_info.get('pron')}")
        lines.append(furigana_info["note_zh"])
    if not local["curriculum"] and not local["false_friends"]:
        lines.append("课文和同形词库里没有直接命中。")
    return _emit(args, local, "\n".join(lines) + "\n")


def _cmd_reference(args: argparse.Namespace) -> int:
    from oto.pronounce.reference import merge_reference

    ref = merge_reference(
        args.text,
        load_curriculum(),
        reading=args.reading,
        accent=args.accent,
    )
    lines = [f"{args.text}"]
    if ref.get("pattern_zh"):
        lines.append(ref["pattern_zh"])
    if ref.get("reading"):
        lines.append(f"读音 {ref['reading']} · 来源 {ref.get('source')}")
    if ref.get("pron"):
        lines.append(f"发音形 {ref['pron']}")
    if ref.get("note_zh"):
        lines.append(ref["note_zh"])
    if ref.get("disagreement_zh"):
        lines.append(ref["disagreement_zh"])
    if ref.get("words") and not ref.get("pattern_zh"):
        for word in ref["words"]:
            lines.append(
                f"{word['surface']} {word['reading']} 核 {word['accent']} / {word['morae']} 拍  {word.get('pron')}"
            )
        if ref.get("note_zh"):
            lines.append(ref["note_zh"])
    return _emit(args, ref, "\n".join(lines) + "\n")


def _cmd_speak(args: argparse.Namespace) -> int:
    from oto.pronounce.tts import synthesize

    result = synthesize(args.text, Path(args.output), engine=args.engine, accent=args.accent)
    if not result.get("available"):
        print(result.get("reason", "合成失败"), file=sys.stderr)
        return 1
    lines = [
        f"已写入 {result['path']}",
        f"引擎 {result['engine']}",
        f"署名 {result.get('credit', '')}",
        result.get("note_zh", ""),
    ]
    return _emit(args, result, "\n".join(lines) + "\n")


def _cmd_analyze(args: argparse.Namespace) -> int:
    from oto.pronounce.analyze import analyze

    chart = Path(args.chart) if args.chart else None
    result = analyze(
        Path(args.audio),
        args.text,
        load_curriculum(),
        reading=args.reading,
        accent=args.accent,
        chart=chart,
        use_hatsuon=not args.no_hatsuon,
    )
    if args.transcribe:
        from oto.pronounce.asr import transcribe

        result["transcript"] = transcribe(args.audio)
    ref = result["reference"]
    lines = [f"分析 {args.text}", ""]
    if ref.get("pattern_zh"):
        lines.append(ref["pattern_zh"])
    f0 = result["f0"]
    median = f0.get("median_hz")
    median_text = "无" if median is None else f"{median:.0f} Hz"
    lines.append(
        f"F0 后端 {f0.get('backend')}，浊音帧 {f0.get('voiced_frames')}，中位 {median_text}。"
    )
    if result.get("chart"):
        lines.append(f"图 {result['chart']}")
    if result.get("chart_error"):
        lines.append(f"画图失败：{result['chart_error']}")
    hatsuon = result.get("hatsuon") or {}
    if hatsuon.get("available"):
        lines.append(
            f"hatsuon 综合 {hatsuon['overall']}，准确 {hatsuon['accuracy']}，"
            f"重音 {hatsuon['pitch']}，信心 {hatsuon['confidence']}。"
        )
        lines.append(hatsuon["disclaimer_zh"])
        for word in hatsuon.get("words") or []:
            bits = " ".join(_mora_bit(mora) for mora in word["morae"])
            lines.append(
                f"  {word['surface']} {word['reading']} 词分 {word['score']} "
                f"重音结果 {word['accent']} 核 {word['accent_type']} {bits}"
            )
    elif hatsuon:
        lines.append(f"hatsuon 未用：{hatsuon.get('reason')}")
    transcript = result.get("transcript") or {}
    if transcript.get("available"):
        lines.append(
            f"转写 {transcript.get('engine')} {transcript.get('compute_type') or ''}："
            f"{transcript.get('text')}"
        )
        if transcript.get("note_zh"):
            lines.append(transcript["note_zh"])
    elif transcript:
        lines.append(f"转写未用：{transcript.get('reason')}")
    lines.append("")
    lines.append("提醒（看的是目标音，不是诊断）")
    for reminder in result["reminders_zh"]:
        lines.append(f"- {reminder['zh']}")
    lines.append("")
    lines.append(result["disclaimer_zh"])
    return _emit(args, result, "\n".join(lines) + "\n")


def _mora_bit(mora: dict) -> str:
    pitch = mora.get("pitch_status") or "—"
    level = mora.get("expected_level") or "—"
    return f"{mora['kana']}:{mora['status']}/{mora['score']}/预期{level}/音高{pitch}"


def _cmd_pitch(args: argparse.Namespace) -> int:
    from oto.pronounce.audio import read_wav
    from oto.pronounce.f0 import extract_f0
    from oto.pronounce.plot import plot_trio
    from oto.pronounce.reference import merge_reference
    from oto.pronounce.tts import synthesize

    out = Path(args.output)
    particle = args.particle or ""
    rows = []
    details = []
    credits = []
    engines = []
    for word in args.words:
        lexical = word[: -len(particle)] if particle and word.endswith(particle) else word
        spoken_text = f"{lexical}{particle}" if particle else word
        wav = out.with_name(out.stem + f"-{spoken_text}.wav")
        spoken = synthesize(spoken_text, wav, engine=args.engine)
        if not spoken.get("available"):
            raise RuntimeError(spoken.get("reason") or f"{spoken_text} 合成失败")
        ref = merge_reference(lexical, load_curriculum())
        samples, sample_rate = read_wav(wav)
        track = extract_f0(samples, sample_rate)
        if not ref.get("morae"):
            raise RuntimeError(f"{lexical} 没有单字重音型，不能放进对照图。")
        morae = list(ref["morae"])
        levels = list(ref["levels"])
        if particle:
            morae = [*morae, particle]
            levels = list(ref.get("levels_with_particle") or levels)
        rows.append(
            {
                "surface": lexical,
                "spoken": spoken_text,
                "reading": ref.get("reading"),
                "type": ref.get("type"),
                "accent": ref.get("accent"),
                "morae": morae,
                "levels": levels,
                "times": track["times"],
                "freqs": track["freqs"],
            }
        )
        details.append(
            {
                "word": lexical,
                "spoken": spoken_text,
                "wav": str(wav),
                "engine": spoken.get("engine"),
                "reference": {
                    "type": ref.get("type"),
                    "accent": ref.get("accent"),
                    "reading": ref.get("reading"),
                },
                "f0": track["summary"],
                "credit": spoken.get("credit"),
            }
        )
        if spoken.get("credit"):
            credits.append(spoken["credit"])
        if spoken.get("engine"):
            engines.append(spoken["engine"])
    engine_name = engines[0] if engines else args.engine
    title = f"{' '.join(args.words)} 的实测 F0（{engine_name}）"
    caption = "曲线是合成音的基频，不是学习者录音。朱红字是教材重音型，没有对齐到时间上。"
    if particle:
        caption += f" 短语带助词「{particle}」，用来分开尾高和平板。"
    else:
        caption += " 无助词时，尾高和平板的合成曲线可能重合。"
    if credits:
        caption += " 署名：" + "；".join(dict.fromkeys(credits)) + "。"
    plot_trio(out, rows, title=title, caption=caption)
    payload = {"chart": str(out), "items": details, "engine": engine_name}
    credit_line = ""
    if credits:
        credit_line = "署名 " + "；".join(dict.fromkeys(credits)) + "。\n"
    return _emit(
        args,
        payload,
        f"已写入 {out}\n引擎 {engine_name}。曲线是合成音，不是学习者。\n{credit_line}",
    )


def _cmd_export(args: argparse.Namespace) -> int:
    curriculum = load_curriculum()
    pitfalls = load_pitfalls()
    state = None if args.all else load_state(_state_path(args))
    if state is not None and not state.get("introduced"):
        state = None
        # An empty profile would export nothing. Say so, unless --all.
        if not args.all:
            raise ValueError("档案里还没有学过的条目。加 --all 导出整个课程。")
    rows = list(iter_cards(curriculum, None if args.all else state, pitfalls))
    path = Path(args.output)
    if args.format == "csv":
        write_csv(path, rows)
    else:
        write_apkg(path, rows)
    payload = {"path": str(path), "rows": len(rows), "format": args.format}
    return _emit(args, payload, f"已写入 {path}，{len(rows)} 条。Anki 会重新安排间隔。\n")


def _jsonable_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Drop nothing important; cards are already plain dicts."""
    return plan


if __name__ == "__main__":
    raise SystemExit(main())
