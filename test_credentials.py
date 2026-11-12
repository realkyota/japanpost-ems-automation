import unittest
from credentials import SERVICE, ACCOUNT, save_login, load_saved, forget_login

class FakeKeychain:
    def __init__(self): self.records = {}
    def set_password(self, service, account, value): self.records[service, account] = value
    def get_password(self, service, account): return self.records.get((service, account))
    def delete_password(self, service, account): del self.records[service, account]

class CredentialTests(unittest.TestCase):
    def test_save_load_delete(self):
        backend = FakeKeychain()
        self.assertIsNone(load_saved(backend))
        save_login(' example@example.com ', 'FAKE_TEST_SECRET', backend)
        self.assertEqual(load_saved(backend), {'username': 'example@example.com', 'password': 'FAKE_TEST_SECRET'})
        forget_login(backend)
        self.assertIsNone(load_saved(backend))
        forget_login(backend)
    def test_invalid_credentials_not_saved(self):
        backend = FakeKeychain()
        with self.assertRaises(RuntimeError): save_login('', 'FAKE_TEST_SECRET', backend)
        self.assertEqual(backend.records, {})
    def test_corrupt_record_hides_its_contents(self):
        backend = FakeKeychain()
        backend.records[SERVICE, ACCOUNT] = 'CORRUPT_PRIVATE_DATA'
        with self.assertRaises(RuntimeError) as error: load_saved(backend)
        self.assertNotIn('CORRUPT_PRIVATE_DATA', str(error.exception))
    def test_backend_failure_does_not_fall_back_to_file(self):
        backend = FakeKeychain()
        def fail(*args): raise OSError('FAKE_TEST_SECRET')
        backend.set_password = fail
        with self.assertRaises(RuntimeError) as error: save_login('example@example.com', 'FAKE_TEST_SECRET', backend)
        self.assertNotIn('FAKE_TEST_SECRET', str(error.exception))
        self.assertEqual(backend.records, {})

if __name__ == '__main__': unittest.main()
