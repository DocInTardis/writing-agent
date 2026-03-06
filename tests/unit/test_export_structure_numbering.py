from writing_agent.web.domains import export_structure_domain


def test_figure_numbering_sequential_passes() -> None:
    text = "\n".join(
        [
            "# 标题",
            "## 引言",
            "图1 系统架构",
            "## 方法",
            "图2 流程图",
        ]
    )
    ok, meta = export_structure_domain._figure_numbering_is_sequential(text)
    assert ok is True
    assert meta["numbers"] == [1, 2]


def test_figure_numbering_gap_fails() -> None:
    text = "\n".join(
        [
            "# 标题",
            "## 引言",
            "图1 系统架构",
            "## 方法",
            "图3 流程图",
        ]
    )
    ok, meta = export_structure_domain._figure_numbering_is_sequential(text)
    assert ok is False
    assert meta["numbers"] == [1, 3]


def test_table_numbering_gap_fails() -> None:
    text = "\n".join(
        [
            "# 标题",
            "## 结果",
            "表2 指标对比",
            "## 讨论",
            "表4 消融实验",
        ]
    )
    ok, meta = export_structure_domain._table_numbering_is_sequential(text)
    assert ok is False
    assert meta["numbers"] == [2, 4]
