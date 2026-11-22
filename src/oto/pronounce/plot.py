"""Charts for a measured F0 track and the expected high/low pattern.

The expected pattern is drawn in its own panel. It is not stretched across
the waveform and passed off as a time alignment.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def plot_analysis(
    path: Path,
    *,
    samples: np.ndarray,
    sample_rate: int,
    times: np.ndarray,
    freqs: np.ndarray,
    title: str,
    levels: list[str] | None,
    morae: list[str] | None,
    caption: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font_path in (
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/tmp/oto-fonts/ZenOldMincho-Regular.ttf",
    ):
        if Path(font_path).is_file():
            font_manager.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = "WenQuanYi Micro Hei"
    plt.rcParams["axes.unicode_minus"] = False

    ink = "#1C1917"
    paper = "#F4F0E7"
    blue = "#243044"
    vermilion = "#C24532"
    muted = "#8A8178"

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(10.4, 6.6),
        dpi=140,
        gridspec_kw={"height_ratios": [1.05, 1.55, 0.72]},
    )
    fig.patch.set_facecolor(paper)
    duration = len(samples) / sample_rate if sample_rate else 0
    axis_time = np.arange(len(samples)) / sample_rate

    axes[0].plot(axis_time, samples, color=ink, linewidth=0.6)
    axes[0].set_xlim(0, max(duration, 0.01))
    axes[0].set_ylabel("振幅")
    axes[0].set_title(title, loc="left", color=ink, fontsize=13, pad=10)

    voiced = freqs > 0
    axes[1].plot(times[voiced], freqs[voiced], color=blue, linewidth=1.4)
    axes[1].set_xlim(0, max(duration, 0.01))
    axes[1].set_ylabel("F0（Hz）")
    axes[1].set_xlabel("时间（秒）")

    if levels and morae:
        for index, (mora, level) in enumerate(zip(morae, levels)):
            color = vermilion if level == "H" else muted
            axes[2].bar(index, 1 if level == "H" else 0.38, color=color, width=0.72)
            axes[2].text(index, 1.08, mora, ha="center", va="bottom", color=ink, fontsize=12)
        axes[2].set_xlim(-0.6, len(levels) - 0.4)
        axes[2].set_ylim(0, 1.45)
        axes[2].set_yticks([0.38, 1.0])
        axes[2].set_yticklabels(["低", "高"])
        axes[2].set_xticks([])
        axes[2].set_ylabel("教材型")
    else:
        axes[2].text(0.02, 0.5, "没有单词语调型可画。", transform=axes[2].transAxes, color=muted)
        axes[2].set_xticks([])
        axes[2].set_yticks([])

    for axis in axes:
        axis.set_facecolor(paper)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(colors=muted)
        axis.yaxis.label.set_color(muted)

    fig.text(0.01, 0.01, caption, color=muted, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=paper)
    plt.close(fig)


def plot_trio(
    path: Path,
    rows: list[dict],
) -> None:
    """Three synthesized words, each with its own F0 and expected pattern."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_path = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    if Path(font_path).is_file():
        font_manager.fontManager.addfont(font_path)
    plt.rcParams["font.family"] = "WenQuanYi Micro Hei"
    plt.rcParams["axes.unicode_minus"] = False

    paper = "#F4F0E7"
    ink = "#1C1917"
    blue = "#243044"
    vermilion = "#C24532"
    muted = "#8A8178"

    fig, axes = plt.subplots(len(rows), 1, figsize=(10.4, 2.5 * len(rows)), dpi=140, squeeze=False)
    fig.patch.set_facecolor(paper)
    for axis, row in zip(axes[:, 0], rows):
        times = row["times"]
        freqs = row["freqs"]
        voiced = freqs > 0
        axis.plot(times[voiced], freqs[voiced], color=blue, linewidth=1.5)
        axis.set_facecolor(paper)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        label = f"{row['surface']}  {row['reading']}  {row['type']}  核 {row['accent']}"
        axis.set_title(label, loc="left", color=ink, fontsize=12)
        axis.set_ylabel("Hz")
        axis.tick_params(colors=muted)
        pattern = " ".join(
            f"{mora}{'高' if level == 'H' else '低'}" for mora, level in zip(row["morae"], row["levels"])
        )
        axis.text(
            0.99,
            0.86,
            pattern,
            transform=axis.transAxes,
            ha="right",
            va="top",
            color=vermilion,
            fontsize=11,
        )
    fig.suptitle("はし  三词的实测 F0（OpenJTalk 合成）", color=ink, fontsize=14, x=0.02, ha="left")
    fig.text(
        0.01,
        0.005,
        "曲线是合成音的基频，不是学习者录音。朱红字是教材重音型，没有对齐到时间上。无助词时，尾高和平板的合成曲线可能重合。",
        color=muted,
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=paper)
    plt.close(fig)
