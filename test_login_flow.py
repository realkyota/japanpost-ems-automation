import unittest
from japanpost import Bot

class Locator:
    def __init__(self, page, selector): self.page, self.selector = page, selector
    def fill(self, value): self.page.actions.append(('fill', self.selector))
    def press(self, key): self.page.actions.append(('press', key))
    def click(self, **kwargs): self.page.actions.append(('click', self.selector))

class Page:
    def __init__(self, prepared=True, detected=True): self.actions=[]; self.prepared=prepared; self.detected=detected
    def evaluate(self, script, data=None):
        if 'typeof submitCommand' in script:
            self.actions.append(('scripts-ready',))
            return True
        if 'document.body' in script:
            self.actions.append(('wait-for-menu',))
            return 'menu' if self.detected else 'unknown'
        if 'true' not in script: raise AssertionError('must prepare without DOM submit')
        return {'ok': self.prepared, 'message': 'test result'}
    def wait_for_timeout(self, timeout): raise TimeoutError('simulated deadline')
    def locator(self, selector): return Locator(self, selector)
    def wait_for_load_state(self, *args, **kwargs): pass
    def wait_for_function(self, *args, **kwargs):
        if 'submitCommand' in args[0]:
            self.actions.append(('scripts-ready',))
            return
        self.actions.append(('wait-for-menu',))
        if not self.detected: raise TimeoutError()

class LoginBot(Bot):
    def __init__(self,page): self.page=page
    def load_helpers(self): pass

class LoginFlowTests(unittest.TestCase):
    def test_native_click_and_result_detection(self):
        page=Page()
        result=LoginBot(page).login({'username':'example@example.com','password':'FAKE_ONLY'})
        self.assertTrue(result['ok'])
        self.assertEqual([a[0] for a in page.actions], ['scripts-ready','fill','fill','press','click','wait-for-menu'])
    def test_failed_preparation_never_clicks(self):
        page=Page(prepared=False)
        self.assertFalse(LoginBot(page).login({'username':'example@example.com','password':'FAKE_ONLY'})['ok'])
        self.assertEqual(page.actions,[('scripts-ready',)])
    def test_no_menu_not_reported_as_success_or_retried(self):
        page=Page(detected=False)
        self.assertFalse(LoginBot(page).login({'username':'example@example.com','password':'FAKE_ONLY'})['ok'])
        self.assertEqual(sum(a[0]=='click' for a in page.actions),1)

if __name__=='__main__': unittest.main()
