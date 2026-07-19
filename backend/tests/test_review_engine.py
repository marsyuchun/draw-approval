import unittest

from app.review_engine import DrawingReviewEngine


class DrawingReviewEngineTest(unittest.TestCase):
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
