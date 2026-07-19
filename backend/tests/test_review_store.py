import tempfile
import unittest
from pathlib import Path

from app.review_store import ReviewStore


class ReviewStoreTest(unittest.TestCase):
    def test_save_upload_and_report_can_be_read_back(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReviewStore(Path(temp_dir))
            upload = store.save_upload("part.dxf", b"0\nDIM 12 mm")
            report = {
                "id": upload.review_id,
                "file": {"name": "part.dxf"},
                "issues": [],
                "summary": {"totalIssues": 0},
            }

            store.save_report(report)
            loaded = store.get_report(upload.review_id)

            self.assertTrue(upload.path.exists())
            self.assertEqual(loaded["id"], upload.review_id)
            self.assertEqual(loaded["file"]["name"], "part.dxf")

    def test_delete_report_removes_report_and_related_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ReviewStore(Path(temp_dir))
            upload = store.save_upload("part.dxf", b"0\nDIM 12 mm", review_id="review-001")
            store.save_report({"id": "review-001", "file": {"name": "part.dxf"}})

            store.delete_report("review-001")

            self.assertFalse(upload.path.exists())
            with self.assertRaises(FileNotFoundError):
                store.get_report("review-001")


if __name__ == "__main__":
    unittest.main()
