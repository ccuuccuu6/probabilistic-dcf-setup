"""Original-byte and numeric provenance audits, independent of AI/network calls."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from research_platform.evidence import verify_model_input_sources


class ModelSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        book = Workbook()
        book.active.title = "Original"
        book.active["A1"] = -12
        book.active["A2"] = 2.5
        book.active["A4"] = "—"
        book.save(self.root / "original.xlsx")
        self.data = {"sources": {"src": self.source("original.xlsx", "xlsx")},
                     "historical": {}, "segments": [], "interims": []}

    def source(self, path, format_name):
        return dict(id="src", local_path=path, format=format_name,
                    sha256=hashlib.sha256((self.root / path).read_bytes()).hexdigest())

    def ref(self, cell="A1", raw=-12, multiplier=1, **kwargs):
        return dict(source_id="src", sheet="Original", cell=cell, raw=raw,
                    multiplier=multiplier, **kwargs)

    def point(self, value, refs):
        self.data["historical"]["measure"] = dict(label="Measure", unit="currency",
            values={"2025": value}, sources={"2025": refs})

    def failures(self, data=None):
        return [check for check in verify_model_input_sources(data or self.data, self.root)
                if check["status"] == "FAIL"]

    def test_signed_value_and_unit_conversion_are_both_checked(self):
        self.point(.025, [self.ref("A2", 2.5, .01)])
        self.assertEqual(self.failures(), [])
        self.data["historical"]["measure"]["sources"]["2025"][0]["multiplier"] = 1
        self.assertTrue(self.failures())
        self.point(12, [self.ref(raw=12)])
        self.assertTrue(self.failures())

    def test_derived_values_use_explicit_weighted_originals(self):
        self.point(-7, [self.ref(contribution_weight=1),
                        self.ref("A2", 2.5, contribution_weight=2)])
        self.assertEqual(self.failures(), [])
        self.data["historical"]["measure"]["values"]["2025"] = -6
        self.assertEqual(len(self.failures()), 1)

    def test_changed_original_and_missing_raw_are_rejected(self):
        self.point(-12, [self.ref()])
        bad = copy.deepcopy(self.data)
        del bad["historical"]["measure"]["sources"]["2025"][0]["raw"]
        self.assertTrue(self.failures(bad))
        with (self.root / "original.xlsx").open("ab") as stream:
            stream.write(b"changed")
        self.assertTrue(any(c["area"] == "source_integrity" for c in self.failures()))

    def test_blank_caches_and_none_do_not_become_zero(self):
        self.point(0, [self.ref("A3", 0)])
        self.assertTrue(self.failures())
        self.point(None, [])
        checks = verify_model_input_sources(self.data, self.root)
        self.assertEqual([c["status"] for c in checks if c["area"] == "source_data"], ["MISSING"])

    def test_optional_absence_stays_none_and_is_a_warning(self):
        self.point(None, [])
        metric = self.data["historical"]["measure"]
        metric.update(optional=True, missing_reason="Optional comparison unavailable; no forecast uses it.")
        checks = verify_model_input_sources(self.data, self.root)
        self.assertIsNone(metric["values"]["2025"])
        self.assertEqual([c["status"] for c in checks if c["area"] == "source_data"], ["WARNING"])

    def test_segments_and_interims_use_the_same_provenance_contract(self):
        self.data["segments"] = [dict(id="segment", sales2025=12,
            source_refs={"sales2025": self.ref(multiplier=-1)})]
        self.data["interims"] = [dict(period="2025-H1", value=-12, source_ref=self.ref())]
        self.assertEqual(self.failures(), [])
        self.data["interims"][0]["value"] = 12
        self.assertEqual(len(self.failures()), 1)

    def test_pdf_presence_is_signed_and_is_not_semantic_acceptance(self):
        writer = PdfWriter()
        page = writer.add_blank_page(600, 800)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 60 740 Td (Charge \\(12\\) and rate 2.5%) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(self.root / "original.pdf")
        self.data["sources"]["src"] = self.source("original.pdf", "pdf")
        self.point(-12, [dict(source_id="src", unit_id="page:1", raw=-12, multiplier=1)])
        checks = verify_model_input_sources(self.data, self.root)
        self.assertFalse([c for c in checks if c["status"] == "FAIL"])
        self.assertTrue(any("semantic mapping is unverified" in c["detail"] for c in checks))
        self.point(12, [dict(source_id="src", unit_id="page:1", raw=12, multiplier=1)])
        self.assertTrue(self.failures())
        self.data["historical"] = {}
        self.data["observations"] = [dict(id="rate", period="2025-H1", value=.025,
            source_refs=[dict(source_id="src", unit_id="page:1", raw="2.5%", multiplier=1)])]
        self.assertEqual(self.failures(), [])
        self.data["observations"][0]["source_refs"][0]["multiplier"] = .01
        self.assertTrue(self.failures(), "Literal percentages must not be divided by 100 twice")

    def test_archive_escape_is_rejected(self):
        self.data["sources"]["src"]["local_path"] = "../original.xlsx"
        self.assertTrue(self.failures())


if __name__ == "__main__":
    unittest.main()
