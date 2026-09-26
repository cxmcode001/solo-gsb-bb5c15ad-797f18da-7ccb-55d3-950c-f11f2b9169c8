"""骑马钉（saddle-stitched）小册子拼版核心算法。

规则概述
--------
1. 每张纸正反两面各印 2 页，对折后 1 张纸 = 4 个版面，因此每册页数必须
   补齐到 4 的倍数，补位页为空白页。
2. 原稿按顺序分册：除最后一册外，每册都装满 ``4 * max_sheets_per_booklet`` 页。
3. 对一册已补齐到 ``n`` 页（``n`` 为 4 的倍数）的小册子，纸张从外到内编号
   为 ``i = 0 .. n/4-1``，每张纸：

   - 正面（front，朝外的一面）：左页 ``n - 2i``，右页 ``1 + 2i``
   - 反面（back，朝内的一面）：左页 ``2 + 2i``，右页 ``n - 1 - 2i``

   按此拼版双面打印（沿短边翻转）并对折后，翻开顺序即为 1, 2, 3, ..., n。
4. 补齐的空白页编号为 0，对外用 ``None``（JSON null）表示。

另支持按章节分册（``build_chapter_imposition``）：章节不可拆分、仅相邻章节
可合册，在每册页数不超过 ``4 * max_sheets_per_booklet`` 的所有方案中依次最小化
总纸张数与册数，并以各册结束章节序号序列的字典序裁决并列。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


class ChapterTooLargeError(ValueError):
    """单章页数超过单册容量（章节不可拆分，无法分册）。"""

    def __init__(self, chapter: int, pages: int, capacity: int) -> None:
        self.chapter = chapter
        self.pages = pages
        self.capacity = capacity
        super().__init__(
            f"第 {chapter} 章共 {pages} 页，超过单册容量上限 {capacity} 页"
            "（4 × max_sheets_per_booklet），章节不可拆分。"
        )


@dataclass(frozen=True)
class BookletRange:
    """一册对应的原稿区间（页码均为 1-based，闭区间）。"""

    index: int
    start_page: int
    end_page: int
    padded_pages: int

    @property
    def original_pages(self) -> int:
        return self.end_page - self.start_page + 1

    @property
    def sheet_count(self) -> int:
        return self.padded_pages // 4

    @property
    def blank_pages(self) -> int:
        return self.padded_pages - self.original_pages


@dataclass(frozen=True)
class ChapterBookletRange:
    """按章节分出的一册：章节区间与全局原稿页区间（均为 1-based 闭区间）。"""

    index: int
    start_chapter: int
    end_chapter: int
    start_page: int
    end_page: int
    padded_pages: int

    @property
    def original_pages(self) -> int:
        return self.end_page - self.start_page + 1

    @property
    def sheet_count(self) -> int:
        return self.padded_pages // 4

    @property
    def blank_pages(self) -> int:
        return self.padded_pages - self.original_pages


def _ceil_to_multiple_of_four(value: int) -> int:
    return ((value + 3) // 4) * 4


def split_booklets(total_pages: int, max_sheets_per_booklet: int) -> list[BookletRange]:
    """把连续原稿页分册，并返回每册补齐到 4 的倍数后的页数。

    分册时先装满前面各册（每册 ``4 * max_sheets_per_booklet`` 页），
    剩余页归入最后一册，仅最后一册可能需要补空白页。
    """
    capacity = 4 * max_sheets_per_booklet
    booklets: list[BookletRange] = []
    start = 1
    index = 0
    while start <= total_pages:
        end = min(total_pages, start + capacity - 1)
        original = end - start + 1
        booklets.append(
            BookletRange(
                index=index,
                start_page=start,
                end_page=end,
                padded_pages=_ceil_to_multiple_of_four(original),
            )
        )
        start = end + 1
        index += 1
    return booklets


def impose_padded_booklet(padded_pages: int) -> list[dict[str, dict[str, int]]]:
    """对一册已补齐到 4 的倍数的版面做拼版。

    返回纸张列表（从外到内），每张纸为
    ``{"front": {"left": ..., "right": ...}, "back": {...}}``，
    页码为该册补齐版面上的 1-based 编号，空白页用 0 表示。
    """
    if padded_pages <= 0 or padded_pages % 4 != 0:
        raise ValueError("padded_pages 必须是正的 4 的倍数")

    n = padded_pages
    sheets: list[dict[str, dict[str, int]]] = []
    for i in range(n // 4):
        sheets.append(
            {
                "front": {"left": n - 2 * i, "right": 1 + 2 * i},
                "back": {"left": 2 + 2 * i, "right": n - 1 - 2 * i},
            }
        )
    return sheets


def _to_original(position: int, booklet: BookletRange | ChapterBookletRange) -> int | None:
    """把补齐版面位置（1-based）映射为原稿页码。

    补白页统一追加在原稿之后，因此位置大于本册原稿页数的版面即为空白页。
    """
    if position > booklet.original_pages:
        return None
    return booklet.start_page + position - 1


def _build_booklet_sheets(
    booklet: BookletRange | ChapterBookletRange,
) -> list[dict]:
    """对一册做拼版，返回从外到内的纸张列表（页码为全局原稿页码，补白为 None）。"""
    layout = impose_padded_booklet(booklet.padded_pages)
    return [
        {
            "index": i,
            "front": {
                "left": _to_original(sheet["front"]["left"], booklet),
                "right": _to_original(sheet["front"]["right"], booklet),
            },
            "back": {
                "left": _to_original(sheet["back"]["left"], booklet),
                "right": _to_original(sheet["back"]["right"], booklet),
            },
        }
        for i, sheet in enumerate(layout)
    ]


def build_imposition(total_pages: int, max_sheets_per_booklet: int) -> dict:
    """完整拼版：分册 -> 补齐 -> 每册从外到内给出正反面左右页码。"""
    booklets = split_booklets(total_pages, max_sheets_per_booklet)
    result_booklets: list[dict] = []

    for booklet in booklets:
        result_booklets.append(
            {
                "index": booklet.index,
                "start_page": booklet.start_page,
                "end_page": booklet.end_page,
                "original_pages": booklet.original_pages,
                "padded_pages": booklet.padded_pages,
                "blank_pages": booklet.blank_pages,
                "sheet_count": booklet.sheet_count,
                "sheets": _build_booklet_sheets(booklet),
            }
        )

    return {
        "total_pages": total_pages,
        "max_sheets_per_booklet": max_sheets_per_booklet,
        "booklet_count": len(booklets),
        "total_sheets": sum(b.sheet_count for b in booklets),
        "booklets": result_booklets,
    }


def split_chapter_booklets(
    chapter_pages: Sequence[int], max_sheets_per_booklet: int
) -> list[ChapterBookletRange]:
    """按章节分册：章节不可拆分，仅相邻章节可合入同一册。

    每册页数不得超过 ``4 * max_sheets_per_booklet``。在所有满足该约束的
    分册方案中，依次按以下目标择优：

    1. 总纸张数最小（每册纸张数 = 册内页数补齐到 4 的倍数后 ÷ 4）；
    2. 册数最小；
    3. 各册结束章节序号（1-based）组成的序列字典序最小。

    任一章节页数超过单册容量时抛出 :class:`ChapterTooLargeError`。
    """
    capacity = 4 * max_sheets_per_booklet
    chapters = list(chapter_pages)
    for position, pages in enumerate(chapters, start=1):
        if pages > capacity:
            raise ChapterTooLargeError(position, pages, capacity)

    n = len(chapters)
    prefix = [0] * (n + 1)
    for i, pages in enumerate(chapters, start=1):
        prefix[i] = prefix[i - 1] + pages

    # 动态规划：best[i] 为前 i 章的最优 (总纸张数, 册数, 结束章节序号序列)，
    # 三者按字典序比较即对应上述依次最小化的择优目标。
    best: list[tuple[int, int, tuple[int, ...]] | None] = [None] * (n + 1)
    best[0] = (0, 0, ())
    for i in range(1, n + 1):
        for j in range(i - 1, -1, -1):
            pages = prefix[i] - prefix[j]
            if pages > capacity:
                break
            prev = best[j]
            if prev is None:
                continue
            candidate = (
                prev[0] + _ceil_to_multiple_of_four(pages) // 4,
                prev[1] + 1,
                prev[2] + (i,),
            )
            if best[i] is None or candidate < best[i]:
                best[i] = candidate

    # 单章超容量已在上游拒绝，最优分册必然存在。
    assert best[n] is not None
    end_chapters = best[n][2]

    booklets: list[ChapterBookletRange] = []
    start_chapter = 1
    for index, end_chapter in enumerate(end_chapters):
        start_page = prefix[start_chapter - 1] + 1
        end_page = prefix[end_chapter]
        booklets.append(
            ChapterBookletRange(
                index=index,
                start_chapter=start_chapter,
                end_chapter=end_chapter,
                start_page=start_page,
                end_page=end_page,
                padded_pages=_ceil_to_multiple_of_four(end_page - start_page + 1),
            )
        )
        start_chapter = end_chapter + 1
    return booklets


def build_chapter_imposition(
    chapter_pages: Sequence[int], max_sheets_per_booklet: int
) -> dict:
    """按章节分册的完整拼版：最优分册 -> 补齐 -> 每册从外到内给出正反面左右页码。

    页码为全局原稿页码（跨册连续编号），补白页为 ``None``。
    """
    chapters = list(chapter_pages)
    booklets = split_chapter_booklets(chapters, max_sheets_per_booklet)
    result_booklets: list[dict] = []

    for booklet in booklets:
        result_booklets.append(
            {
                "index": booklet.index,
                "start_chapter": booklet.start_chapter,
                "end_chapter": booklet.end_chapter,
                "start_page": booklet.start_page,
                "end_page": booklet.end_page,
                "original_pages": booklet.original_pages,
                "padded_pages": booklet.padded_pages,
                "blank_pages": booklet.blank_pages,
                "sheet_count": booklet.sheet_count,
                "sheets": _build_booklet_sheets(booklet),
            }
        )

    return {
        "chapter_pages": chapters,
        "max_sheets_per_booklet": max_sheets_per_booklet,
        "chapter_count": len(chapters),
        "total_pages": sum(chapters),
        "booklet_count": len(booklets),
        "total_sheets": sum(b.sheet_count for b in booklets),
        "total_blank_pages": sum(b.blank_pages for b in booklets),
        "booklets": result_booklets,
    }


def build_reprint(
    total_pages: int,
    max_sheets_per_booklet: int,
    damaged_ranges: Iterable[tuple[int, int]],
) -> dict:
    """按现有分册与拼版规则，定位承载受损原稿页的整张纸（补印清单）。

    ``damaged_ranges`` 为若干 ``(start_page, end_page)`` 闭区间（1-based），
    调用方（schema 层）需已保证区间非倒置、未越界且列表非空。

    - 区间允许相互交叠：同一纸张只返回一次；
    - 结果按分册序号升序、同册纸张从外到内（序号升序）排列；
    - 每张纸给出正反面左右原稿页码（补白为 ``None``）以及落在该纸上的、
      去重升序排列的受损页码。
    """
    damaged_pages: set[int] = set()
    for start, end in damaged_ranges:
        damaged_pages.update(range(start, end + 1))

    imposition = build_imposition(total_pages, max_sheets_per_booklet)
    sheets_out: list[dict] = []

    for booklet in imposition["booklets"]:
        for sheet in booklet["sheets"]:
            page_positions = (
                sheet["front"]["left"],
                sheet["front"]["right"],
                sheet["back"]["left"],
                sheet["back"]["right"],
            )
            hit = sorted(p for p in page_positions if p in damaged_pages)
            if not hit:
                continue
            # build_imposition 的输出本就按分册序号、纸张从外到内排列。
            sheets_out.append(
                {
                    "booklet_index": booklet["index"],
                    "sheet_index": sheet["index"],
                    "front": sheet["front"],
                    "back": sheet["back"],
                    "damaged_pages": hit,
                }
            )

    return {
        "total_pages": total_pages,
        "max_sheets_per_booklet": max_sheets_per_booklet,
        "booklet_count": imposition["booklet_count"],
        "reprint_sheet_count": len(sheets_out),
        "sheets": sheets_out,
    }
