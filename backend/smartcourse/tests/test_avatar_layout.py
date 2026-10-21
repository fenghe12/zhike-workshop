import unittest
from app.avatar_layout import map_avatar_box


class AvatarLayoutTests(unittest.TestCase):
    def test_exact_coordinates_scale_with_canvas(self):
        box = {"img_w": 1920, "img_h": 1080, "x_px": 1200, "y_px": 600, "size_px": 300}
        self.assertEqual(map_avatar_box(box, 960, 540, 200, 200), (600, 300, 150, 150))

    def test_portrait_fits_inside_approved_box(self):
        box = {"img_w": 1000, "img_h": 1000, "x_px": 100, "y_px": 200, "width_px": 300, "height_px": 200}
        self.assertEqual(map_avatar_box(box, 1000, 1000, 100, 200), (200, 200, 100, 200))

    def test_invalid_rectangles_are_rejected(self):
        for fields in [{"x_px": -1}, {"size_px": 0}, {"x_px": 950}, {"y_px": float("nan")}]:
            box = {"img_w": 1000, "img_h": 1000, "x_px": 100, "y_px": 200, "size_px": 200, **fields}
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                map_avatar_box(box, 1000, 1000, 100, 200)
