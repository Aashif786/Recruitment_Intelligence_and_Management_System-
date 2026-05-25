import unittest


from app.core.email_utils import validate_email_strict
from app.core.phone_utils import compute_phone_hash, normalize_phone_digits
from app.core.resume_upload_utils import (
    generate_hashed_resume_filename,
    get_resume_extension,
    validate_resume_signature,
)


class EmailValidationTests(unittest.TestCase):
    def test_numeric_local_part_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_email_strict("123@example.com")
        self.assertIn("Email local part cannot be only numbers", str(ctx.exception))

    def test_disposable_domain_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_email_strict("user@mailinator.com")
        self.assertIn("Disposable email domains", str(ctx.exception))

    def test_normalizes_case_and_whitespace(self):
        # `check_deliverability=False` so example.com should validate without MX/DNS.
        self.assertEqual(validate_email_strict(" User@Example.com "), "user@example.com")

    def test_invalid_format_has_generic_message(self):
        with self.assertRaises(ValueError) as ctx:
            validate_email_strict("not-an-email")
        self.assertIn("Enter a valid email", str(ctx.exception))


class PhoneValidationTests(unittest.TestCase):
    def test_normalizes_digits_only(self):
        digits, reason = normalize_phone_digits("+1 (555) 123-4567")
        self.assertIsNone(reason)
        self.assertEqual(digits, "15551234567")

    def test_rejects_letters(self):
        digits, reason = normalize_phone_digits("abc-def")
        self.assertIsNone(digits)
        self.assertEqual(reason, "letters_present")

    def test_phone_hash_is_deterministic(self):
        digits, reason = normalize_phone_digits("5551234567")
        self.assertIsNone(reason)
        h1 = compute_phone_hash(digits)
        h2 = compute_phone_hash(digits)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


class ResumeUploadSignatureTests(unittest.TestCase):
    def test_pdf_signature_validation(self):
        ok, reason = validate_resume_signature(".pdf", b"%PDF-1.4\n%fake\n")
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_docx_signature_validation(self):
        ok, reason = validate_resume_signature(".docx", b"PK\x03\x04fakezip")
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_signature_mismatch_rejected(self):
        ok, reason = validate_resume_signature(".pdf", b"PK\x03\x04fakezip")
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_pdf_signature")

    def test_hashed_filename_is_safe(self):
        content = b"%PDF-1.4\n%fake\n"
        fname = generate_hashed_resume_filename(
            candidate_email="user@example.com",
            job_id=1,
            resume_ext=".pdf",
            content=content,
        )
        self.assertTrue(fname.endswith(".pdf"))
        self.assertNotIn("/", fname)
        self.assertNotIn("\\", fname)

    def test_extension_extraction(self):
        self.assertEqual(get_resume_extension("resume.PDF"), ".pdf")
        self.assertEqual(get_resume_extension("resume.docx"), ".docx")


if __name__ == "__main__":
    unittest.main()

