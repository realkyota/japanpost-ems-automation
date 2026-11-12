import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from diagnostics import DiagnosticJournal, write_menu_diagnostic
from japanpost import Ledger, UserError, fingerprint, main, validate
from test_japanpost import valid_data


class DiagnosticCreationTests(unittest.TestCase):
    def test_file_exists_even_before_web_inspection(self):
        with TemporaryDirectory() as directory:
            journal=DiagnosticJournal(Path(directory)/'new-output','test-build')
            self.assertTrue(journal.path.exists())
            report=json.loads(journal.path.read_text())
            self.assertEqual(report['build'],'test-build')
            self.assertEqual(report['stage'],'startup')

    def test_failed_dom_inspection_still_writes_valid_report(self):
        class Page:
            url='https://www.int-mypage.post.japanpost.jp/mypage/M010100.do'
            def evaluate(self,script):raise RuntimeError('DOM unavailable')
        with TemporaryDirectory() as directory:
            output=Path(directory)/'not-created-yet'
            path=write_menu_diagnostic(Page(),output,TimeoutError('menu click timed out'))
            self.assertTrue(path.exists())
            report=json.loads(path.read_text())
            self.assertEqual(report['domInspection'],'failed')
            self.assertEqual(report['domInspectionErrorType'],'RuntimeError')
            self.assertEqual(report['exceptionType'],'TimeoutError')

    def test_duplicate_block_before_browser_still_has_report(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);output=root/'output';output.mkdir()
            data=validate(valid_data())
            config=root/'shipment.json';config.write_text(json.dumps(data))
            Ledger(output).attempted(fingerprint(data))
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                with self.assertRaises(UserError):main([str(config),'--output',str(output)])
            path=output/'diagnostic-main-menu.json'
            self.assertTrue(path.exists())
            self.assertIn(str(path),stdout.getvalue())
            report=json.loads(path.read_text())
            self.assertEqual(report['stage'],'exit_exception')
            self.assertIn('防重复',report['events'][-1]['message'])

    def test_missing_configuration_still_has_report(self):
        with TemporaryDirectory() as directory:
            output=Path(directory)/'output'
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(FileNotFoundError):main([str(Path(directory)/'missing.json'),'--output',str(output)])
            report=json.loads((output/'diagnostic-main-menu.json').read_text())
            self.assertEqual(report['events'][-1]['exceptionType'],'FileNotFoundError')

    def test_journal_keeps_menu_metadata(self):
        class Page:
            url='https://www.int-mypage.post.japanpost.jp/mypage/M010100.do'
            def evaluate(self,script):return [{'tag':'IMG','alt':'送り状作成'}]
        with TemporaryDirectory() as directory:
            journal=DiagnosticJournal(directory,'test-build')
            write_menu_diagnostic(Page(),directory,None)
            journal.event('paused')
            report=json.loads(journal.path.read_text())
            self.assertEqual(report['controls'][0]['alt'],'送り状作成')
            self.assertEqual(report['build'],'test-build')

if __name__=='__main__':unittest.main()
