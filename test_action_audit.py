import unittest
from action_audit import ActionAudit

class Page:
    def __init__(self): self.listeners={}
    def on(self, event, callback): self.listeners[event]=callback
    def remove_listener(self, event, callback): self.listeners.pop(event)

class Request:
    method='POST'
    url='https://www.int-mypage.post.japanpost.jp/mypage/M010000.do?not-logged=private'

class Dialog:
    message='Validation error for FAKE_PRIVATE_VALUE'
    def dismiss(self): self.dismissed=True

class AuditTests(unittest.TestCase):
    def test_post_observation_redaction_and_listener_cleanup(self):
        page=Page()
        with ActionAudit(page, ['FAKE_PRIVATE_VALUE']) as audit:
            page.listeners['request'](Request())
            page.listeners['pageerror'](RuntimeError('FAKE_PRIVATE_VALUE https://example.com/?secret=x'))
            dialog=Dialog()
            page.listeners['dialog'](dialog)
            summary=audit.summary()
            self.assertIn('POST 请求：1',summary)
            self.assertNotIn('FAKE_PRIVATE_VALUE',summary)
            self.assertNotIn('secret=x',summary)
            self.assertEqual(audit.posts,['/mypage/M010000.do'])
            self.assertTrue(dialog.dismissed)
        self.assertEqual(page.listeners,{})
        self.assertEqual(audit.secrets,[])
    def test_no_request_is_unknown_not_a_success(self):
        self.assertIn('尚不能确定',ActionAudit(Page()).summary())
    def test_outside_origin_is_not_counted(self):
        req=Request();req.url='https://example.com/login'
        audit=ActionAudit(Page());audit.on_request(req)
        self.assertEqual(audit.posts,[])

if __name__=='__main__': unittest.main()
