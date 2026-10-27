import io
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from app.documents import extrair_texto


class ExtrairTextoTests(unittest.TestCase):
    def test_extracts_csv_rows(self):
        self.assertEqual(
            extrair_texto("gastos.csv", "data,valor\nmercado,42".encode()),
            "data | valor\nmercado | 42",
        )

    def test_extracts_utf8_text(self):
        self.assertEqual(
            extrair_texto("objetivos.txt", "Viagem em dezembro".encode()),
            "Viagem em dezembro",
        )

    def test_extracts_workbook_sheets_and_rows(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Gastos"
        sheet.append(["Data", "Descrição", "Valor"])
        sheet.append(["2026-10-01", "Mercado", 42])
        content = io.BytesIO()
        workbook.save(content)

        texto = extrair_texto("controle.xlsx", content.getvalue())

        self.assertIn("Aba: Gastos", texto)
        self.assertIn("Data | Descrição | Valor", texto)
        self.assertIn("2026-10-01 | Mercado | 42", texto)

    def test_extracts_searchable_pdf_text(self):
        page = unittest.mock.Mock()
        page.extract_text.return_value = "Total da nota: R$ 42,00"
        with patch("app.documents.PdfReader", return_value=unittest.mock.Mock(pages=[page])):
            self.assertEqual(
                extrair_texto("nota.pdf", b"conteudo PDF"),
                "Página 1: Total da nota: R$ 42,00",
            )

    def test_rejects_unsupported_format_and_empty_file(self):
        with self.assertRaisesRegex(ValueError, "Formato não suportado"):
            extrair_texto("arquivo.xls", b"dados")
        with self.assertRaisesRegex(ValueError, "vazio"):
            extrair_texto("arquivo.txt", b"")

    def test_rejects_invalid_workbook_as_input_error(self):
        with self.assertRaisesRegex(ValueError, "XLSX válido"):
            extrair_texto("arquivo.xlsx", b"nao e uma planilha")


if __name__ == "__main__":
    unittest.main()
