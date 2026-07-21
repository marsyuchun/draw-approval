import unittest

from app.review_engine import DrawingReviewEngine
from app.drawing_models import DrawingDimension, DrawingLocation, DrawingText, ParsedDrawing


class DrawingReviewEngineTest(unittest.TestCase):
    def _repeated_unannotated_feature_dxf(self, dimension_text: str = "") -> bytes:
        dimension_entity = ""
        if dimension_text:
            dimension_entity = f"""0
TEXT
8
DIMS
10
45
20
15
40
2.5
1
{dimension_text}
"""
        return f"""0
SECTION
2
ENTITIES
0
TEXT
8
TITLE
10
0
20
0
40
2.5
1
1:5
0
LINE
8
0
10
10
20
10
11
10
21
20
0
LINE
8
0
10
13
20
10
11
13
21
20
0
LINE
8
0
10
10
20
20
11
13
21
20
0
LINE
8
0
10
40
20
40
11
40
21
50
0
LINE
8
0
10
43
20
40
11
43
21
50
0
LINE
8
0
10
40
20
50
11
43
21
50
{dimension_entity}0
ENDSEC
0
EOF
""".encode()

    def _sample_pdf(self, text: str = "DIM 20 mm") -> bytes:
        import fitz

        document = fitz.open()
        page = document.new_page(width=320, height=220)
        page.insert_text((40, 80), text)
        payload = document.tobytes()
        document.close()
        return payload

    def _nearby_duplicate_pdf(self) -> bytes:
        import fitz

        document = fitz.open()
        page = document.new_page(width=600, height=420)
        page.insert_text((100, 100), "100")
        page.insert_text((170, 112), "100")
        page.insert_text((480, 110), "100")
        payload = document.tobytes()
        document.close()
        return payload

    def _three_diameter_pdf(self) -> bytes:
        import fitz

        document = fitz.open()
        page = document.new_page(width=600, height=420)
        page.insert_text((100, 100), "100")
        page.insert_text((170, 112), "100")
        page.insert_text((480, 110), "100")
        payload = document.tobytes()
        document.close()
        return payload

    def test_same_value_dimensions_in_different_locations_are_not_duplicate_issues(self):
        content = b"""0
SECTION
2
ENTITIES
0
TEXT
8
DIMS
10
20
20
10
40
2.5
1
DIM 20 mm
0
TEXT
8
DIMS
10
50
20
10
40
2.5
1
DIM 20 mm
0
TEXT
8
DIMS
10
50
20
25
40
2.5
1
DIM -5 mm
0
ENDSEC
0
EOF
"""

        report = DrawingReviewEngine().review(
            filename="shaft.dxf",
            content=content,
            content_type="application/dxf",
        )

        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertNotIn("DUPLICATE_DIMENSION", issue_codes)
        self.assertIn("INVALID_DIMENSION_VALUE", issue_codes)
        self.assertEqual(report["summary"]["totalIssues"], 1)
        self.assertEqual(report["summary"]["critical"], 1)
        self.assertEqual(report["summary"]["warning"], 0)
        self.assertEqual(report["file"]["name"], "shaft.dxf")
        self.assertTrue(report["visual"]["available"])
        self.assertEqual(report["visual"]["kind"], "dxf-overlay")
        self.assertIn("<svg", report["visual"]["baseSvg"])
        self.assertIn("<svg", report["visual"]["overlaySvg"])
        self.assertGreater(report["visual"]["width"], 0)
        self.assertGreater(report["visual"]["height"], 0)
        self.assertEqual(report["visual"]["coordinateSource"], "dxf")
        self.assertIn("data-issue-code=\"INVALID_DIMENSION_VALUE\"", report["visual"]["overlaySvg"])
        self.assertNotIn("class=\"cad-text\">", report["visual"]["overlaySvg"])
        self.assertNotIn("<circle", report["visual"]["overlaySvg"])
        self.assertNotIn("Warning", report["visual"]["overlaySvg"])

    def test_review_flags_duplicate_dimensions_only_when_locations_overlap(self):
        content = b"""0
SECTION
2
ENTITIES
0
TEXT
8
DIMS
10
20
20
10
40
2.5
1
DIM 20 mm
0
TEXT
8
DIMS
10
21
20
10
40
2.5
1
DIM 20 mm
0
ENDSEC
0
EOF
"""

        report = DrawingReviewEngine().review(
            filename="shaft.dxf",
            content=content,
            content_type="application/dxf",
        )

        duplicate_issue = next(issue for issue in report["issues"] if issue["code"] == "DUPLICATE_DIMENSION")
        self.assertEqual(len(duplicate_issue["locations"]), 2)
        self.assertEqual(duplicate_issue["locations"][0]["page"], 1)
        self.assertEqual(duplicate_issue["locations"][0]["source"], "dxf")
        self.assertIn("bbox", duplicate_issue["locations"][0])

    def test_review_flags_repeated_undimensioned_feature_width(self):
        report = DrawingReviewEngine().review(
            filename="support.dxf",
            content=self._repeated_unannotated_feature_dxf(),
            content_type="application/dxf",
        )

        issue = next(issue for issue in report["issues"] if issue["code"] == "MISSING_LINEAR_DIMENSION")
        self.assertEqual(issue["evidence"], ["15 mm", "2 处同值几何间距"])
        self.assertEqual(len(issue["locations"]), 2)
        self.assertIn("data-issue-code=\"MISSING_LINEAR_DIMENSION\"", report["visual"]["overlaySvg"])

    def test_review_does_not_flag_feature_when_linear_dimension_exists(self):
        report = DrawingReviewEngine().review(
            filename="support.dxf",
            content=self._repeated_unannotated_feature_dxf("DIM 15 mm"),
            content_type="application/dxf",
        )

        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertNotIn("MISSING_LINEAR_DIMENSION", issue_codes)

    def test_missing_dimension_locations_are_projected_to_pdf_overlay_coordinates(self):
        def location(x: float, y: float) -> DrawingLocation:
            return DrawingLocation(page=1, source="dxf", bbox={"x": x, "y": y, "width": 2, "height": 2})

        dimensions = [
            DrawingDimension(20, "mm", "DIM 20 mm", location(10, 10)),
            DrawingDimension(30, "mm", "DIM 30 mm", location(20, 20)),
            DrawingDimension(40, "mm", "DIM 40 mm", location(30, 30)),
        ]
        pdf_texts = [
            DrawingText("DIM 20 mm", DrawingLocation(1, "pdf-text", {"x": 30, "y": 390, "width": 4, "height": 4})),
            DrawingText("DIM 30 mm", DrawingLocation(1, "pdf-text", {"x": 50, "y": 370, "width": 4, "height": 4})),
            DrawingText("DIM 40 mm", DrawingLocation(1, "pdf-text", {"x": 70, "y": 350, "width": 4, "height": 4})),
        ]
        parsed = ParsedDrawing(source_format="dxf", confidence="high", dimensions=dimensions)
        issues = [
            {
                "code": "MISSING_LINEAR_DIMENSION",
                "locations": [location(15, 12).to_dict()],
            }
        ]

        projected = DrawingReviewEngine()._project_missing_dimension_locations_to_pdf(issues, parsed, pdf_texts)

        location_payload = projected[0]["locations"][0]
        self.assertEqual(location_payload["source"], "pdf-dxf-geometry")
        self.assertAlmostEqual(location_payload["bbox"]["x"], 40)
        self.assertAlmostEqual(location_payload["bbox"]["y"], 386)

    def test_review_notices_when_bushing_diameters_lack_a_section_view(self):
        outer_diameter = DrawingDimension(
            100,
            "mm",
            "%%c100",
            DrawingLocation(1, "dxf", {"x": 20, "y": 20, "width": 5, "height": 2}),
        )
        inner_diameter = DrawingDimension(
            60,
            "mm",
            "%%c60",
            DrawingLocation(1, "dxf", {"x": 35, "y": 20, "width": 5, "height": 2}),
        )
        parsed = ParsedDrawing(source_format="dxf", confidence="high", dimensions=[outer_diameter, inner_diameter])

        notices = DrawingReviewEngine()._check_bushing_depth_clarity(parsed)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["code"], "BUSHING_DEPTH_UNCLEAR")
        self.assertEqual(notices[0]["severity"], "Notice")
        self.assertEqual(notices[0]["title"], "轴套深度尺寸不明确")

    def test_section_view_suppresses_bushing_depth_notice(self):
        outer_diameter = DrawingDimension(
            100,
            "mm",
            "%%c100",
            DrawingLocation(1, "dxf", {"x": 20, "y": 20, "width": 5, "height": 2}),
        )
        inner_diameter = DrawingDimension(
            60,
            "mm",
            "%%c60",
            DrawingLocation(1, "dxf", {"x": 35, "y": 20, "width": 5, "height": 2}),
        )
        section_text = DrawingText("剖视图 A-A", DrawingLocation(1, "dxf", {"x": 0, "y": 0, "width": 10, "height": 2}))
        parsed = ParsedDrawing(
            source_format="dxf",
            confidence="high",
            texts=[section_text],
            dimensions=[outer_diameter, inner_diameter],
        )

        notices = DrawingReviewEngine()._check_bushing_depth_clarity(parsed)

        self.assertEqual(notices, [])

    def test_review_pair_uses_pdf_as_base_and_dxf_for_overlay(self):
        dxf_content = b"""0
SECTION
2
ENTITIES
0
TEXT
8
DIMS
10
20
20
10
40
2.5
1
DIM -5 mm
0
TEXT
8
DIMS
10
50
20
10
40
2.5
1
DIM 20 mm
0
ENDSEC
0
EOF
"""

        report = DrawingReviewEngine().review_pair(
            dxf_filename="shaft.dxf",
            dxf_content=dxf_content,
            pdf_filename="shaft.pdf",
            pdf_content=self._sample_pdf("DIM -5 mm"),
        )

        self.assertEqual(report["engine"]["mode"], "pdf-dxf-pair")
        self.assertEqual(report["file"]["companion"]["name"], "shaft.pdf")
        self.assertEqual(report["visual"]["kind"], "pdf-dxf-overlay")
        self.assertTrue(report["visual"]["baseImage"].startswith("data:image/png;base64,"))
        self.assertIn("data-issue-code=\"INVALID_DIMENSION_VALUE\"", report["visual"]["overlaySvg"])
        self.assertEqual(report["visual"]["coordinateSource"], "pdf-text")

    def test_review_pair_flags_nearby_duplicate_pdf_dimensions(self):
        dxf_content = b"""0
SECTION
2
ENTITIES
0
TEXT
8
DIMS
10
20
20
10
40
2.5
1
DIM 20 mm
0
ENDSEC
0
EOF
"""

        report = DrawingReviewEngine().review_pair(
            dxf_filename="shaft.dxf",
            dxf_content=dxf_content,
            pdf_filename="shaft.pdf",
            pdf_content=self._nearby_duplicate_pdf(),
        )

        nearby_issues = [issue for issue in report["issues"] if issue["code"] == "NEARBY_DUPLICATE_DIMENSION"]
        self.assertEqual(len(nearby_issues), 1)
        self.assertEqual(nearby_issues[0]["evidence"], ["100", "100"])
        self.assertEqual(len(nearby_issues[0]["locations"]), 2)
        self.assertIn("data-issue-code=\"NEARBY_DUPLICATE_DIMENSION\"", report["visual"]["overlaySvg"])

    def test_review_pair_groups_repeated_diameter_dimensions_across_views(self):
        dxf_content = b"""0
SECTION
2
ENTITIES
0
TEXT
8
DIMS
10
20
20
20
40
2.5
1
%%c100
0
TEXT
8
DIMS
10
45
20
22
40
2.5
1
%%c100
0
TEXT
8
DIMS
10
160
20
22
40
2.5
1
%%c100
0
ENDSEC
0
EOF
"""

        report = DrawingReviewEngine().review_pair(
            dxf_filename="shaft.dxf",
            dxf_content=dxf_content,
            pdf_filename="shaft.pdf",
            pdf_content=self._three_diameter_pdf(),
        )

        repeated_issues = [issue for issue in report["issues"] if issue["code"] == "REPEATED_DIAMETER_DIMENSION"]
        nearby_issues = [issue for issue in report["issues"] if issue["code"] == "NEARBY_DUPLICATE_DIMENSION"]
        self.assertEqual(len(repeated_issues), 1)
        self.assertEqual(len(repeated_issues[0]["locations"]), 3)
        self.assertEqual(nearby_issues, [])
        self.assertIn("data-issue-code=\"REPEATED_DIAMETER_DIMENSION\"", report["visual"]["overlaySvg"])

    def test_review_reports_unsupported_format_as_notice(self):
        report = DrawingReviewEngine().review(
            filename="notes.txt",
            content=b"DIM 10 mm",
            content_type="text/plain",
        )

        self.assertEqual(report["summary"]["notice"], 1)
        self.assertEqual(report["issues"][0]["code"], "UNSUPPORTED_FORMAT")

    def test_binary_pdf_without_text_does_not_fake_visual_positions(self):
        report = DrawingReviewEngine().review(
            filename="solidworks-export.pdf",
            content=b"%PDF-1.7\x00\x01\x02",
            content_type="application/pdf",
        )

        self.assertFalse(report["visual"]["available"])
        self.assertEqual(report["visual"]["reason"], "no_text_coordinates")
        self.assertEqual(report["issues"][0]["locations"], [])


if __name__ == "__main__":
    unittest.main()
