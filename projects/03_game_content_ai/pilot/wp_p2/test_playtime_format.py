import unittest

from playtime_format import format_playtime


class FormatPlaytimeTest(unittest.TestCase):
    """WP-P2 1.2節のテストケース T1〜T10。"""

    def test_t1_zero_minutes(self):
        self.assertEqual(format_playtime(0), "0分")

    def test_t2_minutes_only(self):
        self.assertEqual(format_playtime(45), "45分")

    def test_t3_exact_one_hour(self):
        self.assertEqual(format_playtime(60), "1時間")

    def test_t4_hour_and_minutes(self):
        self.assertEqual(format_playtime(90), "1時間30分")

    def test_t5_hours_and_single_digit_minutes(self):
        self.assertEqual(format_playtime(125), "2時間5分")

    def test_t6_exact_twenty_four_hours(self):
        self.assertEqual(format_playtime(1440), "24時間")

    def test_t7_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            format_playtime(-1)

    def test_t8_str_raises_type_error(self):
        with self.assertRaises(TypeError):
            format_playtime("90")

    def test_t9_bool_raises_type_error(self):
        with self.assertRaises(TypeError):
            format_playtime(True)

    def test_t10_float_raises_type_error(self):
        with self.assertRaises(TypeError):
            format_playtime(1.5)
