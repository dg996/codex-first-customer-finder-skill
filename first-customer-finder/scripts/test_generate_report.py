#!/usr/bin/env python3
"""Tests for generate_report.py and the report JSON contract.

Runs as a standalone script:

    python3 scripts/test_generate_report.py

Or with pytest:

    pytest scripts/test_generate_report.py

Uses only the Python standard library. If the optional `jsonschema` package is
installed, the example fixture is also validated against
references/report.schema.json; otherwise that check self-skips.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
EXAMPLES_DIR = SKILL_DIR / "examples"
REFERENCES_DIR = SKILL_DIR / "references"

sys.path.insert(0, str(SCRIPT_DIR))
import generate_report as gen  # noqa: E402


def load_example() -> dict:
    with (EXAMPLES_DIR / "analysis.example.json").open("r", encoding="utf-8") as h:
        return json.load(h)


def score_from_dimensions(d: dict) -> int:
    return round(
        d["pain_strength"] / 5 * 25
        + d["product_fit"] / 5 * 25
        + d["timing"] / 5 * 20
        + d["reachability"] / 5 * 15
        + d["evidence_quality"] / 5 * 15
    )


class FixtureContractTests(unittest.TestCase):
    def test_example_has_required_top_level_keys(self):
        data = load_example()
        for key in ("title", "product", "product_url", "target_customer",
                    "generated_at", "verdict", "prospects"):
            self.assertIn(key, data, f"missing top-level key: {key}")

    def test_example_has_three_prospects(self):
        data = load_example()
        self.assertEqual(len(data["prospects"]), 3)

    def test_example_prospects_have_required_keys(self):
        data = load_example()
        required = ("name", "type", "stage", "score", "pain_signal",
                    "why_fit", "why_now", "source_url", "dimensions")
        for p in data["prospects"]:
            for key in required:
                self.assertIn(key, p, f"prospect missing key: {key}")

    def test_example_scores_match_formula(self):
        data = load_example()
        for p in data["prospects"]:
            self.assertEqual(p["score"], score_from_dimensions(p["dimensions"]),
                             f"score mismatch for {p['name']}")

    def test_example_scores_in_valid_bands(self):
        data = load_example()
        for p in data["prospects"]:
            self.assertGreaterEqual(p["score"], 0)
            self.assertLessEqual(p["score"], 100)

    def test_example_source_urls_are_http(self):
        data = load_example()
        for p in data["prospects"]:
            self.assertTrue(p["source_url"].startswith(("http://", "https://")),
                            f"non-http source_url: {p['source_url']}")

    def test_example_dimensions_in_range(self):
        data = load_example()
        for p in data["prospects"]:
            for key, value in p["dimensions"].items():
                self.assertIsInstance(value, int)
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 5, f"{key}={value} out of 0-5")

    def test_example_stages_are_valid(self):
        data = load_example()
        valid = {"High intent", "Problem aware", "Trigger present", "Potential fit"}
        for p in data["prospects"]:
            self.assertIn(p["stage"], valid, f"invalid stage: {p['stage']}")


class GeneratorTests(unittest.TestCase):
    def test_build_html_returns_non_empty(self):
        html = gen.build_html(load_example())
        self.assertGreater(len(html), 1000)

    def test_build_html_contains_prospect_names(self):
        html = gen.build_html(load_example())
        for p in load_example()["prospects"]:
            self.assertIn(p["name"], html)

    def test_build_html_contains_scores(self):
        data = load_example()
        html = gen.build_html(data)
        for p in data["prospects"]:
            self.assertIn(str(p["score"]), html)

    def test_build_html_embeds_export_buttons(self):
        html = gen.build_html(load_example())
        self.assertIn('data-action="export-csv"', html)
        self.assertIn('data-action="export-json"', html)
        self.assertIn('data-action="copy-summary"', html)

    def test_build_html_embeds_report_json(self):
        html = gen.build_html(load_example())
        self.assertIn('id="prospect-data"', html)

    def test_embedded_json_is_parseable_and_matches(self):
        import re
        html = gen.build_html(load_example())
        m = re.search(r'<script type="application/json" id="prospect-data">(.*?)</script>', html, re.S)
        self.assertIsNotNone(m, "prospect-data script not found")
        embedded = json.loads(m.group(1))
        self.assertEqual(embedded["prospects"], load_example()["prospects"])

    def test_golden_html_matches_generator_output(self):
        html = gen.build_html(load_example())
        golden = (EXAMPLES_DIR / "first-customer-finder-report.golden.html").read_text(encoding="utf-8")
        self.assertEqual(html, golden)

    def test_clamps_out_of_range_scores(self):
        data = load_example()
        data["prospects"][0]["score"] = 999
        html = gen.build_html(data)
        self.assertIn(">100<", html)

    def test_handles_empty_prospects(self):
        data = load_example()
        data["prospects"] = []
        html = gen.build_html(data)
        self.assertIn("No qualified prospects supplied", html)

    def test_handles_missing_dimensions(self):
        data = load_example()
        del data["prospects"][0]["dimensions"]
        html = gen.build_html(data)
        self.assertIn("/5</b>", html)

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out" / "report.html"
            input_path = EXAMPLES_DIR / "analysis.example.json"
            sys.argv = ["generate_report.py", str(input_path), str(out)]
            try:
                gen.main()
            finally:
                sys.argv = ["generate_report.py"]
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1000)


class SchemaTests(unittest.TestCase):
    def test_fixture_validates_against_schema(self):
        try:
            import jsonschema  # type: ignore
        except ImportError:
            self.skipTest("jsonschema not installed; schema check skipped")
        schema = json.loads((REFERENCES_DIR / "report.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(load_example(), schema)


if __name__ == "__main__":
    unittest.main(verbosity=2)
