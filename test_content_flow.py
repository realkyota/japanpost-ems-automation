import unittest
from japanpost import Bot, UserError, country_option, validate
from test_japanpost import valid_data


class Control:
    def __init__(self, page, key): self.page, self.key = page, key
    def get_attribute(self, name): return '100'
    def fill(self, value): self.page.values[self.key] = value; self.page.actions.append(('fill', self.key))
    def select_option(self, label=None, value=None):
        if label is not None:
            if label != 'JPY/円': raise AssertionError('wrong currency')
            value = 'JPY'
        self.page.values[self.key] = value
        self.page.actions.append(('select', self.key, value))
        return [value]
    def locator(self, selector):
        if selector.startswith('img'):
            class Empty:
                def count(self): return 0
            return Empty()
        return self
    def evaluate_all(self, script): return [{'value': '392', 'label': 'JAPAN（日本）'}]
    def input_value(self): return self.page.values.get(self.key, '')
    def press(self, key): self.page.actions.append(('press', key))
    def click(self, **kwargs):
        self.page.actions.append(('click', self.key))
        if self.key == 'confirm': self.page.registered = True


class Page:
    def __init__(self, existing=False): self.values={}; self.actions=[]; self.registered=existing
    def locator(self, selector):
        key = selector.split('data-jp-content-')[1].split('=')[0]
        return Control(self, key)
    def evaluate(self, script):
        if script == 'markContentInputs()':
            self.actions.append(('inputs-check',))
            return {'ok': True}
        if script == 'registeredContents()':
            return [{'name':'SAMPLE ITEM','quantity':'1'}] if self.registered else []
        return {'ok':True}
    def wait_for_function(self, *args, **kwargs): self.actions.append(('wait',))


class ContentBot(Bot):
    def __init__(self, page):
        self.page = page
        self.data = valid_data()
        self.data['shipment']['item'].update(unitPrice='100', weightGrams='100')
        self.data['shipment'].pop('totalWeightGrams')
        validate(self.data)
    def load_helpers(self): pass
    def wait_ready(self): pass


class ContentTests(unittest.TestCase):
    def test_bilingual_japan_option_and_duplicates(self):
        self.assertEqual(country_option([{'value':'392','label':'JAPAN（日本）'}], 'JP'), '392')
        with self.assertRaises(UserError):
            country_option([{'value':'a','label':'JAPAN'},{'value':'b','label':'日本'}], 'JP')
    def test_origin_required_and_hs_not_inferred(self):
        data = valid_data()
        data['shipment']['item'].pop('origin', None)
        with self.assertRaises(UserError):
            validate(data)
        data['shipment']['item']['origin'] = 'JP'
        data['shipment']['item'].pop('hsCode', None)
        validate(data)
        self.assertNotIn('hsCode', data['shipment']['item'])
    def test_ems_native_click_before_waiting_for_inputs(self):
        page = Page()
        ContentBot(page).select_ems_goods()
        self.assertEqual(page.actions, [('click','service'), ('inputs-check',)])
    def test_fills_selects_and_confirms_exact_requested_values(self):
        page = Page()
        ContentBot(page).fill_and_confirm_item()
        self.assertEqual(page.values, {'name':'SAMPLE ITEM','unitPrice':'100','weightGrams':'100','hsCode':'000000','quantity':'1','currency':'JPY','origin':'392'})
        self.assertEqual([a for a in page.actions if a[0]=='click'], [('click','confirm')])
        self.assertTrue(page.registered)
    def test_existing_registered_item_never_added_again(self):
        page = Page(existing=True)
        with self.assertRaises(UserError): ContentBot(page).fill_and_confirm_item()
        self.assertEqual(page.actions, [])


if __name__ == '__main__': unittest.main()
