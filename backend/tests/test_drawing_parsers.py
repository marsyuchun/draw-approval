import io
import unittest

import ezdxf

from app.drawing_parser import ParserFactory, UnsupportedDrawingParser


SAMPLE_DXF = b"""0
SECTION
2
ENTITIES
0
LINE
8
GEOMETRY
10
0
20
0
11
100
21
0
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


class DrawingParserTest(unittest.TestCase):
    def test_factory_prefers_dxf_parser_for_dxf_files(self):
        parser = ParserFactory().for_file("part.dxf", "application/dxf")

        self.assertEqual(parser.kind, "dxf")

    def test_dxf_parser_extracts_text_lines_dimensions_and_svg_coordinates(self):
        parser = ParserFactory().for_file("part.dxf", "application/dxf")

        parsed = parser.parse("part.dxf", SAMPLE_DXF)

        self.assertEqual(parsed.source_format, "dxf")
        self.assertEqual(len(parsed.lines), 1)
        self.assertEqual(len(parsed.texts), 3)
        self.assertEqual([dimension.value for dimension in parsed.dimensions], [20.0, 20.0, -5.0])
        self.assertEqual(parsed.dimensions[0].location.source, "dxf")
        self.assertGreater(parsed.dimensions[0].location.bbox["width"], 0)
        self.assertIn("<svg", parsed.preview_svg)
        self.assertTrue(parsed.render["available"])
        self.assertEqual(parsed.render["kind"], "dxf-rendered-svg")
        self.assertIn("baseSvg", parsed.render)
        self.assertGreater(parsed.render["width"], 0)
        self.assertGreater(parsed.render["height"], 0)

    def test_dxf_parser_handles_crlf_files_from_real_cad_exports(self):
        parser = ParserFactory().for_file("part.dxf", "application/dxf")

        parsed = parser.parse("part.dxf", SAMPLE_DXF.replace(b"\n", b"\r\n"))

        self.assertEqual(len(parsed.lines), 1)
        self.assertEqual(len(parsed.texts), 3)
        self.assertEqual(len(parsed.dimensions), 3)

    def test_dimension_text_parsing_prefers_displayed_dimension_value(self):
        parser = ParserFactory().for_file("part.dxf", "application/dxf")

        self.assertEqual(parser._parse_dimension_value("160", 80.0), 160.0)
        self.assertEqual(parser._parse_dimension_value("R12", 6.0), 12.0)
        self.assertEqual(parser._parse_dimension_value("<>", 52.0), 52.0)

    def test_dxf_parser_recursively_extracts_insert_virtual_entities(self):
        document = ezdxf.new("R2000")
        block = document.blocks.new("SYMBOL")
        block.add_line((0, 0), (10, 0))
        block.add_text("DIM 10 mm", dxfattribs={"height": 2.5}).set_placement((0, 5))
        document.modelspace().add_blockref("SYMBOL", (20, 30))
        stream = io.StringIO()
        document.write(stream)

        parser = ParserFactory().for_file("block.dxf", "application/dxf")
        parsed = parser.parse("block.dxf", stream.getvalue().encode("utf-8"))

        self.assertEqual(len(parsed.lines), 1)
        self.assertEqual(len(parsed.texts), 1)
        self.assertEqual(parsed.texts[0].value, "DIM 10 mm")
        self.assertEqual([dimension.value for dimension in parsed.dimensions], [10.0])
        self.assertGreaterEqual(parsed.lines[0].start[0], 20)

    def test_pdf_parser_reports_missing_optional_dependencies_without_fake_coordinates(self):
        parser = ParserFactory().for_file("drawing.pdf", "application/pdf")

        parsed = parser.parse("drawing.pdf", b"%PDF-1.7")

        self.assertEqual(parsed.source_format, "pdf")
        self.assertIn(parsed.confidence, {"low", "none"})
        self.assertEqual(parsed.dimensions, [])
        self.assertEqual(parsed.preview_svg, "")

    def test_unsupported_parser_keeps_strategy_notice(self):
        parser = ParserFactory().for_file("part.step", "application/step")

        self.assertIsInstance(parser, UnsupportedDrawingParser)
        parsed = parser.parse("part.step", b"")

        self.assertEqual(parsed.source_format, "unsupported")
        self.assertEqual(parsed.warnings[0]["code"], "UNSUPPORTED_FORMAT")


if __name__ == "__main__":
    unittest.main()
