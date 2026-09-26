"""拼版核心算法单元测试（仅依赖标准库，可直接 `python -m unittest` 运行）。"""

import unittest

from app.imposition import (
    BindingCheckError,
    ChapterTooLargeError,
    _min_swap_steps,
    build_binding_check,
    build_chapter_imposition,
    build_imposition,
    build_reprint,
    impose_padded_booklet,
    split_booklets,
    split_chapter_booklets,
)


class TestSplitBooklets(unittest.TestCase):
    def test_single_booklet_within_capacity(self):
        ranges = split_booklets(total_pages=10, max_sheets_per_booklet=4)
        self.assertEqual(len(ranges), 1)
        self.assertEqual((ranges[0].start_page, ranges[0].end_page), (1, 10))
        self.assertEqual(ranges[0].padded_pages, 12)
        self.assertEqual(ranges[0].blank_pages, 2)
        self.assertEqual(ranges[0].sheet_count, 3)

    def test_exact_multiple_of_four_no_padding(self):
        ranges = split_booklets(total_pages=16, max_sheets_per_booklet=4)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].padded_pages, 16)
        self.assertEqual(ranges[0].blank_pages, 0)

    def test_multiple_booklets_only_last_is_padded(self):
        # 每册 2 张纸 = 8 页；17 页 -> 8 + 8 + 1
        ranges = split_booklets(total_pages=17, max_sheets_per_booklet=2)
        self.assertEqual(len(ranges), 3)
        self.assertEqual((ranges[0].start_page, ranges[0].end_page), (1, 8))
        self.assertEqual(ranges[0].padded_pages, 8)
        self.assertEqual(ranges[0].blank_pages, 0)
        self.assertEqual((ranges[1].start_page, ranges[1].end_page), (9, 16))
        self.assertEqual(ranges[1].padded_pages, 8)
        self.assertEqual(ranges[1].blank_pages, 0)
        self.assertEqual((ranges[2].start_page, ranges[2].end_page), (17, 17))
        self.assertEqual(ranges[2].padded_pages, 4)
        self.assertEqual(ranges[2].blank_pages, 3)
        self.assertEqual(ranges[0].index, 0)
        self.assertEqual(ranges[2].index, 2)

    def test_one_page_padded_to_four(self):
        ranges = split_booklets(total_pages=1, max_sheets_per_booklet=1)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].padded_pages, 4)
        self.assertEqual(ranges[0].sheet_count, 1)

    def test_capacity_equal_multiple_of_four(self):
        # 总页数恰好装满两册
        ranges = split_booklets(total_pages=16, max_sheets_per_booklet=2)
        self.assertEqual(len(ranges), 2)
        self.assertEqual([r.original_pages for r in ranges], [8, 8])


class TestImposePaddedBooklet(unittest.TestCase):
    def test_four_sheets_classic_layout(self):
        # 16 页 / 4 张纸的经典骑马钉拼版
        sheets = impose_padded_booklet(16)
        self.assertEqual(len(sheets), 4)
        # 最外一张：正面 16|1，反面 2|15
        self.assertEqual(sheets[0]["front"], {"left": 16, "right": 1})
        self.assertEqual(sheets[0]["back"], {"left": 2, "right": 15})
        # 第二张：正面 14|3，反面 4|13
        self.assertEqual(sheets[1]["front"], {"left": 14, "right": 3})
        self.assertEqual(sheets[1]["back"], {"left": 4, "right": 13})
        # 第三张：正面 12|5，反面 6|11
        self.assertEqual(sheets[2]["front"], {"left": 12, "right": 5})
        self.assertEqual(sheets[2]["back"], {"left": 6, "right": 11})
        # 最内一张：正面 10|7，反面 8|9
        self.assertEqual(sheets[3]["front"], {"left": 10, "right": 7})
        self.assertEqual(sheets[3]["back"], {"left": 8, "right": 9})

    def test_single_sheet_padded(self):
        # 4 页 1 张纸
        sheets = impose_padded_booklet(4)
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0]["front"], {"left": 4, "right": 1})
        self.assertEqual(sheets[0]["back"], {"left": 2, "right": 3})

    def test_invalid_inputs(self):
        for bad in (0, -4, 6, 10):
            with self.assertRaises(ValueError):
                impose_padded_booklet(bad)


def _reading_order(sheets):
    """模拟对折后翻阅顺序：按纸张从外到内，依次取正面左、反面左、
    反面右、正面右（骑马钉嵌套书帖的物理翻阅序）。"""
    order = []
    for sheet in sheets:
        order.extend(
            [
                sheet["front"]["left"],
                sheet["back"]["left"],
                sheet["back"]["right"],
                sheet["front"]["right"],
            ]
        )
    return order


class TestFoldingReadingOrder(unittest.TestCase):
    """对折后的核心不变量：正反页码互补为 n+1，且偶数页始终在左、奇数页在右。"""

    def test_pair_sums_and_parity(self):
        for n in (4, 8, 12, 16, 20, 40):
            sheets = impose_padded_booklet(n)
            seen = set()
            for sheet in sheets:
                for side in ("front", "back"):
                    left, right = sheet[side]["left"], sheet[side]["right"]
                    self.assertEqual(left + right, n + 1, f"n={n} 左右页码之和应为 n+1")
                    self.assertEqual(left % 2, 0, "左页必为偶数页")
                    self.assertEqual(right % 2, 1, "右页必为奇数页")
                    seen.update((left, right))
            self.assertEqual(seen, set(range(1, n + 1)), f"n={n} 所有版面应恰好出现一次")

    def test_reading_order_of_a_sheet(self):
        # 单张纸（4 页）对折后翻阅顺序为 4,2,3,1：
        # 背面封面 4 -> 内左 2 -> 内右 3 -> 封面 1。
        # 内页正文顺序即 1(封面) -> 2 -> 3 -> 4(封底)。
        sheets = impose_padded_booklet(4)
        self.assertEqual(_reading_order(sheets), [4, 2, 3, 1])


class TestBuildImposition(unittest.TestCase):
    def test_16_pages_2_sheets_per_booklet_splits_and_maps_original_pages(self):
        result = build_imposition(total_pages=16, max_sheets_per_booklet=2)
        self.assertEqual(result["booklet_count"], 2)
        self.assertEqual(result["total_sheets"], 4)

        first = result["booklets"][0]
        self.assertEqual((first["start_page"], first["end_page"]), (1, 8))
        # 第 1 册 8 页 / 2 张纸
        self.assertEqual(first["sheets"][0]["front"], {"left": 8, "right": 1})
        self.assertEqual(first["sheets"][0]["back"], {"left": 2, "right": 7})
        self.assertEqual(first["sheets"][1]["front"], {"left": 6, "right": 3})
        self.assertEqual(first["sheets"][1]["back"], {"left": 4, "right": 5})

        second = result["booklets"][1]
        # 第 2 册页码从原稿第 9 页重新映射
        self.assertEqual((second["start_page"], second["end_page"]), (9, 16))
        self.assertEqual(second["sheets"][0]["front"], {"left": 16, "right": 9})
        self.assertEqual(second["sheets"][0]["back"], {"left": 10, "right": 15})

    def test_padding_blanks_are_null_and_contiguous_at_inner_end(self):
        # 5 页、1 张纸/册：仅 1 册，补齐到 8 页，3 个空白
        result = build_imposition(total_pages=5, max_sheets_per_booklet=10)
        booklet = result["booklets"][0]
        self.assertEqual(booklet["blank_pages"], 3)
        self.assertEqual(booklet["padded_pages"], 8)
        self.assertEqual(booklet["sheet_count"], 2)
        # 外纸：8(空)|1 / 2|7(空)
        self.assertEqual(booklet["sheets"][0]["front"], {"left": None, "right": 1})
        self.assertEqual(booklet["sheets"][0]["back"], {"left": 2, "right": None})
        # 内纸：6(空)|3 / 4|5
        self.assertEqual(booklet["sheets"][1]["front"], {"left": None, "right": 3})
        self.assertEqual(booklet["sheets"][1]["back"], {"left": 4, "right": 5})

    def test_single_page_booklet(self):
        result = build_imposition(total_pages=1, max_sheets_per_booklet=1)
        booklet = result["booklets"][0]
        self.assertEqual(booklet["blank_pages"], 3)
        # 4|1(原稿1) / 2(空)|3(空)
        self.assertEqual(booklet["sheets"][0]["front"], {"left": None, "right": 1})
        self.assertEqual(booklet["sheets"][0]["back"], {"left": None, "right": None})

    def test_every_original_page_appears_exactly_once(self):
        for total, cap in ((1, 1), (5, 2), (17, 2), (33, 3), (100, 4)):
            result = build_imposition(total_pages=total, max_sheets_per_booklet=cap)
            pages = []
            for booklet in result["booklets"]:
                for sheet in booklet["sheets"]:
                    for side in ("front", "back"):
                        for pos in ("left", "right"):
                            value = sheet[side][pos]
                            if value is not None:
                                pages.append(value)
            self.assertEqual(
                sorted(pages),
                list(range(1, total + 1)),
                f"total={total}, cap={cap}",
            )

    def test_summary_fields(self):
        result = build_imposition(total_pages=17, max_sheets_per_booklet=2)
        self.assertEqual(result["total_pages"], 17)
        self.assertEqual(result["max_sheets_per_booklet"], 2)
        self.assertEqual(result["booklet_count"], 3)
        self.assertEqual(result["total_sheets"], 2 + 2 + 1)


class TestSplitChapterBooklets(unittest.TestCase):
    def test_adjacent_chapters_merged_within_capacity(self):
        # 容量 8 页：[6,5,3] -> 第 1 章单独成册，第 2、3 章合册（6+5=11 > 8 不能三合）
        ranges = split_chapter_booklets([6, 5, 3], max_sheets_per_booklet=2)
        self.assertEqual(
            [(r.start_chapter, r.end_chapter) for r in ranges], [(1, 1), (2, 3)]
        )
        self.assertEqual(
            [(r.start_page, r.end_page) for r in ranges], [(1, 6), (7, 14)]
        )
        self.assertEqual(ranges[0].padded_pages, 8)
        self.assertEqual(ranges[0].blank_pages, 2)
        self.assertEqual(ranges[0].sheet_count, 2)
        self.assertEqual(ranges[1].padded_pages, 8)
        self.assertEqual(ranges[1].blank_pages, 0)
        self.assertEqual([r.index for r in ranges], [0, 1])

    def test_single_chapter_per_booklet_when_nothing_merges(self):
        # 每章 6 页、容量 8：任何两章都超容量，只能各自成册
        ranges = split_chapter_booklets([6, 6, 6], max_sheets_per_booklet=2)
        self.assertEqual(
            [(r.start_chapter, r.end_chapter) for r in ranges],
            [(1, 1), (2, 2), (3, 3)],
        )

    def test_total_sheets_minimized_before_booklet_count(self):
        # [2,2,2] 容量 8：合成一册 6 页 2 张纸，与拆成两册同为 2 张纸，
        # 但册数更少 -> 选一册方案
        ranges = split_chapter_booklets([2, 2, 2], max_sheets_per_booklet=2)
        self.assertEqual(len(ranges), 1)
        self.assertEqual((ranges[0].start_chapter, ranges[0].end_chapter), (1, 3))
        self.assertEqual(ranges[0].sheet_count, 2)

    def test_total_sheets_beats_greedy_fill(self):
        # [4,1,1,4,1,1] 容量 8：顺序装满得 [4,1,1][4,1,1] 共 4 张纸；
        # 最优为 [4][1,1,4,1,1] 共 1+2=3 张纸
        ranges = split_chapter_booklets([4, 1, 1, 4, 1, 1], max_sheets_per_booklet=2)
        self.assertEqual(sum(r.sheet_count for r in ranges), 3)
        self.assertEqual(
            [(r.start_chapter, r.end_chapter) for r in ranges], [(1, 1), (2, 6)]
        )

    def test_ending_chapter_sequence_lexicographic_tie_break(self):
        # [4,1,4] 容量 8：[4][1,4] 与 [4,1][4] 同为 3 张纸、2 册，
        # 结束章节序号序列 [1,3] < [2,3] -> 选 [4][1,4]
        ranges = split_chapter_booklets([4, 1, 4], max_sheets_per_booklet=2)
        self.assertEqual(sum(r.sheet_count for r in ranges), 3)
        self.assertEqual(
            [(r.start_chapter, r.end_chapter) for r in ranges], [(1, 1), (2, 3)]
        )

    def test_chapter_exceeding_capacity_raises(self):
        # 容量 8 页，第 2 章 9 页不可拆分 -> 抛错
        with self.assertRaises(ChapterTooLargeError) as ctx:
            split_chapter_booklets([4, 9, 4], max_sheets_per_booklet=2)
        self.assertEqual(ctx.exception.chapter, 2)
        self.assertEqual(ctx.exception.pages, 9)
        self.assertEqual(ctx.exception.capacity, 8)

    def test_exact_capacity_chapter_fits(self):
        ranges = split_chapter_booklets([8, 4], max_sheets_per_booklet=2)
        self.assertEqual(
            [(r.start_chapter, r.end_chapter) for r in ranges], [(1, 1), (2, 2)]
        )
        self.assertEqual(ranges[0].blank_pages, 0)


class TestBuildChapterImposition(unittest.TestCase):
    def test_booklet_fields_and_global_page_ranges(self):
        result = build_chapter_imposition([6, 5, 3], max_sheets_per_booklet=2)
        self.assertEqual(result["chapter_pages"], [6, 5, 3])
        self.assertEqual(result["chapter_count"], 3)
        self.assertEqual(result["total_pages"], 14)
        self.assertEqual(result["booklet_count"], 2)
        self.assertEqual(result["total_sheets"], 4)
        self.assertEqual(result["total_blank_pages"], 2)

        first, second = result["booklets"]
        self.assertEqual((first["start_chapter"], first["end_chapter"]), (1, 1))
        self.assertEqual((first["start_page"], first["end_page"]), (1, 6))
        self.assertEqual(first["original_pages"], 6)
        self.assertEqual(first["padded_pages"], 8)
        self.assertEqual(first["blank_pages"], 2)
        self.assertEqual(first["sheet_count"], 2)
        self.assertEqual((second["start_chapter"], second["end_chapter"]), (2, 3))
        self.assertEqual((second["start_page"], second["end_page"]), (7, 14))
        self.assertEqual(second["blank_pages"], 0)

    def test_sheets_use_global_pages_and_null_blanks(self):
        result = build_chapter_imposition([6, 5, 3], max_sheets_per_booklet=2)
        first = result["booklets"][0]
        # 第 1 册 6 页补齐到 8：外纸 8(空)|1 / 2|7(空)
        self.assertEqual(first["sheets"][0]["front"], {"left": None, "right": 1})
        self.assertEqual(first["sheets"][0]["back"], {"left": 2, "right": None})
        self.assertEqual(first["sheets"][1]["front"], {"left": 6, "right": 3})
        self.assertEqual(first["sheets"][1]["back"], {"left": 4, "right": 5})
        # 第 2 册 8 页，页码为全局原稿页码 7..14
        second = result["booklets"][1]
        self.assertEqual(second["sheets"][0]["front"], {"left": 14, "right": 7})
        self.assertEqual(second["sheets"][0]["back"], {"left": 8, "right": 13})
        self.assertEqual(second["sheets"][1]["front"], {"left": 12, "right": 9})
        self.assertEqual(second["sheets"][1]["back"], {"left": 10, "right": 11})

    def test_every_original_page_appears_exactly_once(self):
        cases = (
            ([1], 1),
            ([4, 1, 4], 2),
            ([6, 5, 3], 2),
            ([3, 3, 3, 3], 2),
            ([2, 7, 1, 4, 8], 3),
        )
        for chapters, cap in cases:
            result = build_chapter_imposition(chapters, cap)
            pages = []
            for booklet in result["booklets"]:
                for sheet in booklet["sheets"]:
                    for side in ("front", "back"):
                        for pos in ("left", "right"):
                            value = sheet[side][pos]
                            if value is not None:
                                pages.append(value)
            self.assertEqual(
                sorted(pages),
                list(range(1, sum(chapters) + 1)),
                f"chapters={chapters}, cap={cap}",
            )

    def test_single_chapter_too_large_raises(self):
        with self.assertRaises(ChapterTooLargeError):
            build_chapter_imposition([2, 9], max_sheets_per_booklet=2)


class TestBuildReprint(unittest.TestCase):
    def test_single_damaged_page_locates_outer_sheet(self):
        # 16 页 1 册 4 张纸：第 1 页位于最外一张正面右
        result = build_reprint(16, 4, [(1, 1)])
        self.assertEqual(result["reprint_sheet_count"], 1)
        self.assertEqual(result["booklet_count"], 1)
        sheet = result["sheets"][0]
        self.assertEqual((sheet["booklet_index"], sheet["sheet_index"]), (0, 0))
        self.assertEqual(sheet["front"], {"left": 16, "right": 1})
        self.assertEqual(sheet["back"], {"left": 2, "right": 15})
        self.assertEqual(sheet["damaged_pages"], [1])

    def test_range_spanning_multiple_sheets_and_sides(self):
        # 16 页：受损 1..4 -> 外纸（1,2）与第二张（3,4）
        result = build_reprint(16, 4, [(1, 4)])
        self.assertEqual(result["reprint_sheet_count"], 2)
        self.assertEqual(
            [(s["booklet_index"], s["sheet_index"]) for s in result["sheets"]],
            [(0, 0), (0, 1)],
        )
        self.assertEqual(result["sheets"][0]["damaged_pages"], [1, 2])
        self.assertEqual(result["sheets"][1]["damaged_pages"], [3, 4])

    def test_overlapping_ranges_dedupe_sheets_and_pages(self):
        result = build_reprint(16, 4, [(1, 3), (2, 4)])
        # 并集仍为 1..4，落在外两张纸；交叠区间不产生重复纸张
        self.assertEqual(result["reprint_sheet_count"], 2)
        self.assertEqual(result["sheets"][0]["damaged_pages"], [1, 2])
        self.assertEqual(result["sheets"][1]["damaged_pages"], [3, 4])

    def test_sorting_outer_to_inner(self):
        # 16 页：第 11 页落在第三张（index 2），第 9 页落在最内一张（index 3）
        result = build_reprint(16, 4, [(11, 11), (9, 9)])
        self.assertEqual(
            [(s["sheet_index"], s["damaged_pages"]) for s in result["sheets"]],
            [(2, [11]), (3, [9])],
        )

    def test_multi_booklet_sorting_and_indices(self):
        # 17 页、每册 2 张纸（8 页）-> 3 册：受损第 8 页（册0最外纸）与第 9 页（册1最外纸）
        result = build_reprint(17, 2, [(8, 9)])
        self.assertEqual(result["booklet_count"], 3)
        self.assertEqual(result["reprint_sheet_count"], 2)
        first, second = result["sheets"]
        self.assertEqual((first["booklet_index"], first["sheet_index"]), (0, 0))
        self.assertEqual(first["damaged_pages"], [8])
        self.assertEqual((second["booklet_index"], second["sheet_index"]), (1, 0))
        self.assertEqual(second["damaged_pages"], [9])
        # 最后一册存在补白，但不受损、不出现在结果中
        self.assertTrue(all(s["booklet_index"] != 2 for s in result["sheets"]))

    def test_padding_blanks_are_null_but_never_listed_as_damaged(self):
        # 5 页补齐到 8：受损第 5 页 -> 内纸（index 1），外封补白不受影响
        result = build_reprint(5, 10, [(5, 5)])
        self.assertEqual(result["reprint_sheet_count"], 1)
        sheet = result["sheets"][0]
        self.assertEqual(sheet["sheet_index"], 1)
        self.assertEqual(sheet["front"], {"left": None, "right": 3})
        self.assertEqual(sheet["back"], {"left": 4, "right": 5})
        self.assertEqual(sheet["damaged_pages"], [5])

    def test_all_pages_damaged_returns_every_sheet_once(self):
        result = build_reprint(17, 2, [(1, 17)])
        self.assertEqual(result["reprint_sheet_count"], 2 + 2 + 1)
        # 结果按分册序号、纸张从外到内
        keys = [(s["booklet_index"], s["sheet_index"]) for s in result["sheets"]]
        self.assertEqual(
            keys,
            [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)],
        )
        # 每个原稿页都恰好出现在某张纸的 damaged_pages 中一次
        listed = [p for s in result["sheets"] for p in s["damaged_pages"]]
        self.assertEqual(sorted(listed), list(range(1, 18)))

    def test_summary_fields(self):
        result = build_reprint(16, 4, [(15, 16)])
        self.assertEqual(result["total_pages"], 16)
        self.assertEqual(result["max_sheets_per_booklet"], 4)


def _sheet(front_left, front_right, back_left, back_right):
    """构造一条待核对纸张记录。"""
    return {
        "front": {"left": front_left, "right": front_right},
        "back": {"left": back_left, "right": back_right},
    }


# 16 页、每册 4 张纸 -> 单册基准拼版（从外到内）
BOOKLET_16 = [
    _sheet(16, 1, 2, 15),
    _sheet(14, 3, 4, 13),
    _sheet(12, 5, 6, 11),
    _sheet(10, 7, 8, 9),
]


class TestMinSwapSteps(unittest.TestCase):
    def test_already_sorted_needs_no_swap(self):
        self.assertEqual(_min_swap_steps([0, 1, 2, 3]), [])

    def test_single_transposition(self):
        self.assertEqual(_min_swap_steps([1, 0, 2]), [[0, 1]])

    def test_two_disjoint_transpositions(self):
        self.assertEqual(_min_swap_steps([1, 0, 3, 2]), [[0, 1], [2, 3]])

    def test_rotation_uses_min_steps_and_lex_order(self):
        # 循环 0->2->1->0 最少 2 步；可行首步为 (0,1)/(0,2)/(1,2)，
        # 字典序最小的步骤序列为 [(0,1),(1,2)]（而非 [(0,2),(0,1)]）
        self.assertEqual(_min_swap_steps([2, 0, 1]), [[0, 1], [1, 2]])

    def test_four_cycle_lexicographic_sequence(self):
        self.assertEqual(_min_swap_steps([1, 2, 3, 0]), [[0, 1], [0, 2], [0, 3]])

    def test_step_count_matches_cycle_formula(self):
        # 最少步数 = 纸张数 - 循环数
        self.assertEqual(len(_min_swap_steps([3, 2, 1, 0])), 2)
        self.assertEqual(len(_min_swap_steps([2, 3, 0, 1])), 2)


class TestBuildBindingCheck(unittest.TestCase):
    def test_in_order_sheets_need_nothing(self):
        result = build_binding_check(16, 4, 0, BOOKLET_16)
        self.assertEqual(result["sheet_count"], 4)
        self.assertEqual(result["booklet_count"], 1)
        self.assertEqual(
            [(s["current_index"], s["expected_index"]) for s in result["sheets"]],
            [(0, 0), (1, 1), (2, 2), (3, 3)],
        )
        self.assertTrue(all(s["operations"] == [] for s in result["sheets"]))
        self.assertEqual(result["swap_count"], 0)
        self.assertEqual(result["swap_steps"], [])

    def test_shuffled_sheets_positions_and_min_swaps(self):
        shuffled = [BOOKLET_16[1], BOOKLET_16[0], BOOKLET_16[3], BOOKLET_16[2]]
        result = build_binding_check(16, 4, 0, shuffled)
        self.assertEqual(
            [(s["current_index"], s["expected_index"]) for s in result["sheets"]],
            [(0, 1), (1, 0), (2, 3), (3, 2)],
        )
        self.assertEqual(result["swap_count"], 2)
        self.assertEqual(result["swap_steps"], [[0, 1], [2, 3]])

    def test_orientation_operations_detected(self):
        sheets = [
            _sheet(1, 16, 15, 2),  # 第 0 张左右互换
            _sheet(4, 13, 14, 3),  # 第 1 张正反互换
            _sheet(11, 6, 5, 12),  # 第 2 张左右 + 正反
            BOOKLET_16[3],  # 第 3 张原样
        ]
        result = build_binding_check(16, 4, 0, sheets)
        self.assertEqual(
            [s["operations"] for s in result["sheets"]],
            [["left_right"], ["front_back"], ["left_right", "front_back"], []],
        )
        # 各纸位置正确，无需交换
        self.assertEqual(result["swap_steps"], [])

    def test_pages_identified_by_non_empty_set(self):
        result = build_binding_check(16, 4, 0, BOOKLET_16)
        self.assertEqual(
            [s["pages"] for s in result["sheets"]],
            [[1, 2, 15, 16], [3, 4, 13, 14], [5, 6, 11, 12], [7, 8, 9, 10]],
        )

    def test_blank_pages_are_part_of_identity(self):
        # 5 页补齐到 8：外纸含两个补白位，按非空页码集合 {1, 2} / {3, 4, 5} 识别
        sheets = [
            _sheet(None, 3, 4, 5),  # 内纸被放到了最外
            _sheet(None, 1, 2, None),  # 外纸
        ]
        result = build_binding_check(5, 10, 0, sheets)
        self.assertEqual(
            [(s["current_index"], s["expected_index"]) for s in result["sheets"]],
            [(0, 1), (1, 0)],
        )
        self.assertEqual(result["sheets"][0]["pages"], [3, 4, 5])
        self.assertEqual(result["sheets"][1]["pages"], [1, 2])
        self.assertEqual(result["swap_steps"], [[0, 1]])

    def test_multi_booklet_checks_selected_booklet(self):
        # 17 页、每册 2 张纸 -> 3 册；核对第 2 册（全局页码 9..16）
        sheets = [_sheet(14, 11, 12, 13), _sheet(16, 9, 10, 15)]
        result = build_binding_check(17, 2, 1, sheets)
        self.assertEqual(result["booklet_count"], 3)
        self.assertEqual(
            [(s["current_index"], s["expected_index"]) for s in result["sheets"]],
            [(0, 1), (1, 0)],
        )
        self.assertEqual(result["swap_steps"], [[0, 1]])

    def test_missing_sheet_rejected(self):
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, BOOKLET_16[:3])
        self.assertIn("缺纸", str(ctx.exception))

    def test_extra_sheet_rejected(self):
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, BOOKLET_16 + [BOOKLET_16[0]])
        self.assertIn("超出", str(ctx.exception))

    def test_duplicate_sheet_rejected(self):
        sheets = BOOKLET_16[:3] + [BOOKLET_16[2]]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("重复纸", str(ctx.exception))

    def test_cross_booklet_page_rejected(self):
        # 17 页、每册 2 张纸：第 0 册页码范围为 1..8，混入第 9 页即跨册
        sheets = [_sheet(8, 1, 2, 7), _sheet(6, 3, 4, 9)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(17, 2, 0, sheets)
        self.assertIn("跨册页", str(ctx.exception))

    def test_page_beyond_total_pages_rejected_as_cross_booklet(self):
        sheets = BOOKLET_16[:3] + [_sheet(10, 7, 8, 99)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("跨册页", str(ctx.exception))

    def test_unrestorable_layout_rejected(self):
        # 仅反面左右互换（10,7 / 9,8）不在左右互换、正反互换及其组合之内
        sheets = BOOKLET_16[:3] + [_sheet(10, 7, 9, 8)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("无法通过左右互换及正反互换还原", str(ctx.exception))

    def test_unknown_page_combination_rejected(self):
        # 页码都在本册，但组合与任何一张纸都不符
        sheets = BOOKLET_16[:3] + [_sheet(1, 2, 3, 4)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("不符", str(ctx.exception))

    def test_all_blank_sheet_rejected(self):
        sheets = BOOKLET_16[:3] + [_sheet(None, None, None, None)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("全部为空白", str(ctx.exception))

    def test_repeated_page_within_sheet_rejected(self):
        sheets = BOOKLET_16[:3] + [_sheet(10, 7, 8, 8)]
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 0, sheets)
        self.assertIn("重复", str(ctx.exception))

    def test_booklet_index_out_of_range_rejected(self):
        with self.assertRaises(BindingCheckError) as ctx:
            build_binding_check(16, 4, 1, BOOKLET_16)
        self.assertIn("booklet_index 越界", str(ctx.exception))
        self.assertEqual(ctx.exception.field, "booklet_index")

    def test_summary_fields(self):
        result = build_binding_check(17, 2, 2, [_sheet(None, 17, None, None)])
        self.assertEqual(result["total_pages"], 17)
        self.assertEqual(result["max_sheets_per_booklet"], 2)
        self.assertEqual(result["booklet_index"], 2)
        self.assertEqual(result["sheet_count"], 1)
        self.assertEqual(result["sheets"][0]["pages"], [17])


if __name__ == "__main__":
    unittest.main()
