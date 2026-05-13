from __future__ import annotations

import unittest

from app.schemas.procurements import ProcurementLotItem
from app.services.procurement_classification import classify_procurement_lot
from app.services.procurement_sync import prepare_procurement_lot


class ProcurementClassificationTests(unittest.TestCase):
    def test_classifies_medical_apparel(self) -> None:
        classification = classify_procurement_lot(
            ProcurementLotItem(
                external_id="1",
                registry_number="1",
                title="Поставка халатов медицинских и костюмов медицинских",
            )
        )

        self.assertEqual(classification.category, "Медицинская одежда")
        self.assertTrue(classification.is_relevant)
        self.assertIn("халат медицинский", classification.matched_keywords)
        self.assertIn("костюм медицинский", classification.matched_keywords)
        self.assertEqual(classification.excluded_keywords, [])
        self.assertEqual(classification.filter_reason, "matched_category:Медицинская одежда")

    def test_exclusion_keyword_takes_precedence(self) -> None:
        classification = classify_procurement_lot(
            ProcurementLotItem(
                external_id="2",
                registry_number="2",
                title="Поставка спецодежды и ботинок рабочих",
            )
        )

        self.assertEqual(classification.category, "Спецодежда")
        self.assertFalse(classification.is_relevant)
        self.assertIn("спецодежда", classification.matched_keywords)
        self.assertTrue({"ботинки", "ботинок"}.intersection(classification.excluded_keywords))
        self.assertIn(classification.filter_reason, {"excluded_keyword:ботинки", "excluded_keyword:ботинок"})

    def test_neutral_unmatched_tender_is_not_relevant(self) -> None:
        classification = classify_procurement_lot(
            ProcurementLotItem(
                external_id="3",
                registry_number="3",
                title="Поставка мебели для школы",
            )
        )

        self.assertIsNone(classification.category)
        self.assertFalse(classification.is_relevant)
        self.assertEqual(classification.matched_keywords, [])
        self.assertIn("мебель", classification.excluded_keywords)
        self.assertEqual(classification.filter_reason, "excluded_keyword:мебель")

    def test_raw_fields_are_part_of_classification_text(self) -> None:
        classification = classify_procurement_lot(
            ProcurementLotItem(
                external_id="4",
                registry_number="4",
                title="Поставка изделий",
                raw_fields={"Описание": "Изготовление формы для сотрудников учреждения"},
            )
        )

        self.assertEqual(classification.category, "Униформа")
        self.assertIn("форма для сотрудников", classification.matched_keywords)

    def test_prepare_procurement_lot_embeds_classification_in_normalized_payload(self) -> None:
        prepared = prepare_procurement_lot(
            ProcurementLotItem(
                external_id="5",
                registry_number="5",
                title="Пошив спецодежды",
            )
        )

        self.assertEqual(prepared.classification.category, "Спецодежда")
        self.assertEqual(prepared.normalized_item["classification"]["category"], "Спецодежда")
        self.assertTrue(prepared.normalized_item["classification"]["is_relevant"])
