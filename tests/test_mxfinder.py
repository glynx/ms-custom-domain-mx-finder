import unittest

from mxfinder import (
    candidate_list,
    is_microsoft_mx,
    microsoft_mx_records,
    mx_token,
)


class MxTokenTest(unittest.TestCase):
    def test_domains_without_hyphen(self):
        self.assertEqual(mx_token("microsoft.com"), "microsoft-com")
        self.assertEqual(mx_token("atos.net"), "atos-net")
        self.assertEqual(mx_token("example.com."), "example-com")

    def test_domains_with_hyphen(self):
        self.assertEqual(mx_token("british-airways.com"), "britishairways-com01i")
        self.assertEqual(mx_token("van-lanschot.com"), "vanlanschot-com0i")
        self.assertEqual(mx_token("berliner-zeitung.de"), "berlinerzeitung-de02b")
        self.assertEqual(mx_token("john-lewis.co.uk"), "johnlewis-co-uk01b")
        self.assertEqual(mx_token("marks-and-spencer.com"), "marksandspencer-com01cc")

    def test_gist_examples(self):
        self.assertEqual(mx_token("domain-withdash.com"), "domainwithdash-com01e")
        self.assertEqual(mx_token("dom-ainwithdash.com"), "domainwithdash-com0i")

    def test_exact_candidate_comes_first(self):
        candidates = candidate_list("british-airways.com")
        self.assertEqual(candidates[0], "britishairways-com01i")
        self.assertEqual(len(candidates), len(set(candidates)))
        self.assertIn("britishairways-com01e", candidates)

    def test_no_bruteforce(self):
        self.assertEqual(candidate_list("british-airways.com", bruteforce=False), ["britishairways-com01i"])

    def test_microsoft_mx_detection(self):
        self.assertTrue(is_microsoft_mx("britishairways-com01i.mail.protection.outlook.com."))
        self.assertTrue(is_microsoft_mx("example-com.mail.eo.outlook.com"))
        self.assertTrue(is_microsoft_mx("example-com.o-v1.mx.microsoft"))
        self.assertFalse(is_microsoft_mx("mx.noris.net"))
        self.assertFalse(is_microsoft_mx("example-com.mail.protection.outlook.com.evil.test"))

    def test_microsoft_mx_filter(self):
        records = [
            (10, "mx.noris.net"),
            (30, "madeleinemode-com02c.mail.protection.outlook.com"),
        ]
        self.assertEqual(
            microsoft_mx_records(records),
            [(30, "madeleinemode-com02c.mail.protection.outlook.com")],
        )


if __name__ == "__main__":
    unittest.main()
