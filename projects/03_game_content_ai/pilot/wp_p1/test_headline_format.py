import unittest

from headline_format import normalize_headline


class NormalizeHeadlineTest(unittest.TestCase):
    """WP-P1 1.2節の表（T1〜T10）に対応するテスト。"""

    def test_t1_strips_leading_and_trailing_spaces(self):
        self.assertEqual(normalize_headline("  Hello World  "), "Hello World")

    def test_t2_collapses_consecutive_spaces(self):
        self.assertEqual(normalize_headline("Hello    World"), "Hello World")

    def test_t3_collapses_fullwidth_space_tab_and_newline(self):
        self.assertEqual(
            normalize_headline("新作　　発表\t\n速報"),
            "新作 発表 速報",
        )

    def test_t4_exactly_default_max_length_is_unchanged(self):
        self.assertEqual(normalize_headline("a" * 60), "a" * 60)

    def test_t5_over_default_max_length_is_truncated_with_ellipsis(self):
        result = normalize_headline("a" * 61)
        self.assertEqual(result, "a" * 59 + "…")
        self.assertEqual(len(result), 60)

    def test_t6_truncation_removes_trailing_space_before_ellipsis(self):
        self.assertEqual(normalize_headline("abc defgh", max_length=5), "abc…")

    def test_t7_empty_and_whitespace_only_return_empty_string(self):
        self.assertEqual(normalize_headline(""), "")
        self.assertEqual(normalize_headline("　 \t\n"), "")

    def test_t8_none_raises_type_error(self):
        with self.assertRaises(TypeError):
            normalize_headline(None)

    def test_t9_max_length_zero_raises_value_error(self):
        with self.assertRaises(ValueError):
            normalize_headline("abc", max_length=0)

    def test_t10_max_length_one_returns_only_ellipsis(self):
        self.assertEqual(normalize_headline("ab", max_length=1), "…")


if __name__ == "__main__":
    unittest.main()
