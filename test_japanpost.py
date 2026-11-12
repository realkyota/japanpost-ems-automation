import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from japanpost import Bot, Ledger, ORIGIN, UserError, fingerprint, validate


def valid_data():
    data = json.loads(Path(__file__).with_name('shipment.example.json').read_text())
    data.pop('_example')
    return data


class ValidationTests(unittest.TestCase):
    def test_leading_zero_preserved(self):
        data = valid_data()
        data['recipient']['postalCode'] = '00123'
        self.assertEqual(validate(data)['recipient']['postalCode'], '00123')

    def test_example_rejected(self):
        data = valid_data()
        data['_example'] = True
        with self.assertRaises(UserError):
            validate(data)

    def test_reject_incorrect_declarations(self):
        for key, value in [('paid', 'false'), ('paid', True), ('noDangerousGoods', False), ('shipDate', '2026/02/30')]:
            with self.subTest(key=key, value=value):
                data = valid_data()
                data['shipment'][key] = value
                with self.assertRaises(UserError):
                    validate(data)

    def test_bad_weight_and_numeric_postal_code(self):
        data = valid_data()
        data['shipment']['totalWeightGrams'] = '1'
        with self.assertRaises(UserError):
            validate(data)
        data = valid_data()
        data['recipient']['postalCode'] = 123
        with self.assertRaises(UserError):
            validate(data)

    def test_country_and_hs_code(self):
        for field, value in [('country', 'USA'), ('country', 'us')]:
            data = valid_data()
            data['recipient'][field] = value
            with self.assertRaises(UserError):
                validate(data)
        data = valid_data()
        data['shipment']['item']['hsCode'] = 'guess'
        with self.assertRaises(UserError):
            validate(data)


class LedgerTests(unittest.TestCase):
    def test_persisted_attempt_blocks_replay_without_pii(self):
        with TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory))
            data = valid_data()
            key = fingerprint(data)
            ledger.check(key)
            ledger.attempted(key)
            other = Ledger(Path(directory))
            with self.assertRaises(UserError):
                other.check(key)
            other.check(key, allow_repeat=True)
            self.assertNotIn(data['recipient']['name'], ledger.path.read_text())
            self.assertNotIn(data['recipient']['address2'], ledger.path.read_text())


class Events:
    def on(self, *args):
        pass


class Response:
    def __init__(self, url, body):
        self.url, self.content = url, body
        self.headers = {'content-type': 'application/pdf'}

    def body(self):
        return self.content


class PDFTests(unittest.TestCase):
    def test_pdf_bytes_deduplicated_and_non_pdf_refused(self):
        with TemporaryDirectory() as directory:
            bot = Bot(Events(), valid_data(), Path(directory), Events())
            bot.save_pdf(b'<html>not a label</html>')
            self.assertEqual(bot.pdfs, [])
            body = b'%PDF-1.4\nFAKE UNIT TEST PAYLOAD'
            bot.save_pdf(body)
            bot.save_pdf(body)
            self.assertEqual(len(bot.pdfs), 1)
            self.assertEqual(bot.pdfs[0].read_bytes(), body)

    def test_official_origin_only_and_pre_registration_ignored(self):
        with TemporaryDirectory() as directory:
            bot = Bot(Events(), valid_data(), Path(directory), Events())
            official = Response(ORIGIN + '/label', b'%PDF-1.4\nFAKE')
            bot.queue_response(official)
            self.assertFalse(bot.pending_responses)
            bot.printing_enabled = True
            bot.queue_response(Response('https://example.com/label.pdf', b'%PDF-1.4\nFAKE'))
            self.assertFalse(bot.pending_responses)
            bot.queue_response(official)
            bot.collect_pdf()
            self.assertEqual(len(bot.pdfs), 1)


class DummyPage:
    def wait_for_url(self, *args, **kwargs):
        pass


class WorkflowBot(Bot):
    def __init__(self, fail_confirmation=False):
        self.data = valid_data()
        self.page = DummyPage()
        self.actions = []
        self.pdfs = [Path('already-captured-test.pdf')]
        self.fail_confirmation = fail_confirmation

    def step(self, title, operation):
        operation()

    def fill_recipient(self):
        self.actions.append('recipient')

    def wait_for_contents(self):
        self.actions.append('contents_ready')

    def finish_printing(self):
        self.actions.append('official_print')
        return 'print_clicked'

    def click(self, labels):
        self.actions.append(labels[0])

    def operate(self, action):
        self.actions.append(action)

    def confirm_item(self):
        self.actions.append('confirm_item')

    def select_ems_goods(self):
        self.actions.append('ems')

    def fill_and_confirm_item(self):
        self.actions.extend(['item', 'confirm_item'])

    def wait_ready(self):
        pass

    def confirmation(self):
        if self.fail_confirmation:
            raise UserError('confirmation failed')


class WorkflowTests(unittest.TestCase):
    def test_fill_only_never_registers(self):
        with TemporaryDirectory() as directory:
            bot = WorkflowBot()
            ledger = Ledger(Path(directory))
            bot.run(ledger, 'hash', stop_before_register=True)
            self.assertNotIn('register', bot.actions)
            self.assertFalse(ledger.path.exists())

    def test_confirmation_failure_never_registers(self):
        with TemporaryDirectory() as directory:
            bot = WorkflowBot(True)
            ledger = Ledger(Path(directory))
            with self.assertRaises(UserError):
                bot.run(ledger, 'hash', stop_before_register=False)
            self.assertNotIn('register', bot.actions)
            self.assertFalse(ledger.path.exists())

    def test_marked_before_registration_and_single_attempt(self):
        with TemporaryDirectory() as directory:
            bot = WorkflowBot()
            ledger = Ledger(Path(directory))
            old = bot.operate
            def operate(action):
                if action == 'register':
                    self.assertIn('hash', Ledger(Path(directory)).records)
                old(action)
            bot.operate = operate
            bot.run(ledger, 'hash', stop_before_register=False)
            self.assertEqual(bot.actions.count('register'), 1)


if __name__ == '__main__':
    unittest.main()
