from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from japanpost import JST, Ledger, UserError, fingerprint, validate, with_next_day
from test_japanpost import valid_data


class RunDateTests(unittest.TestCase):
    def test_japan_runtime_next_day_overrides_old_json(self):
        data=valid_data();data['shipment']['shipDate']='2020/01/01'
        result=with_next_day(data,datetime(2026,11,12,1,10,tzinfo=JST))
        self.assertEqual(result['shipment']['shipDate'],'2026/11/13')
        self.assertEqual(data['shipment']['shipDate'],'2020/01/01')
    def test_converts_utc_before_choosing_day(self):
        result=with_next_day(valid_data(),datetime(2026,11,11,16,0,tzinfo=timezone.utc))
        self.assertEqual(result['shipment']['shipDate'],'2026/11/13')
    def test_month_year_and_leap_boundaries(self):
        for now,expected in [((2026,12,31),'2027/01/01'),((2028,2,28),'2028/02/29'),((2028,2,29),'2028/03/01')]:
            with self.subTest(now=now):
                result=with_next_day(valid_data(),datetime(*now,tzinfo=JST))
                self.assertEqual(result['shipment']['shipDate'],expected)
    def test_unzoned_time_rejected(self):
        with self.assertRaises(UserError):with_next_day(valid_data(),datetime(2026,11,12))
    def test_automatic_date_does_not_change_input_duplicate_key(self):
        data=validate(valid_data());key=fingerprint(data)
        with TemporaryDirectory() as directory:
            ledger=Ledger(Path(directory));ledger.attempted(key)
            for day in [12,13]:
                with_next_day(data,datetime(2026,11,day,tzinfo=JST))
                self.assertEqual(fingerprint(data),key)
                with self.assertRaises(UserError):ledger.check(key)

if __name__=='__main__':unittest.main()
