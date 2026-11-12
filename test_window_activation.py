import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from diagnostics import write_menu_diagnostic
from japanpost import Bot, ORIGIN, UserError
from page_state import PagePollTimeout
from test_menu import MenuBot, Page


class WindowTests(unittest.TestCase):
    def test_switches_to_official_creation_popup(self):
        main=Page('/menu','マイページメインメニュー')
        child=Page('/sender','ご依頼主を選択する')
        bot=MenuBot(main);bot.context=SimpleNamespace(pages=[main,child])
        self.assertEqual(bot.wait_flow_stage(['sender'],timeout=0),'sender')
        self.assertIs(bot.page,child)
    def test_ignores_nonofficial_window(self):
        main=Page('/sender','ご依頼主を選択する')
        child=Page('/sender','ご依頼主を選択する');child.url='https://example.com/sender'
        bot=MenuBot(main);bot.context=SimpleNamespace(pages=[main,child])
        self.assertEqual(bot.wait_flow_stage(['sender'],timeout=0),'sender')
        self.assertIs(bot.page,main)


class Collection:
    def __init__(self,anchor):self.anchor=anchor
    def count(self):return 1
    def nth(self,index):return self.anchor

class KeyboardTarget:
    def __init__(self,page,events):self.page=page;self.events=events
    def locator(self,selector):return Collection(self)
    def is_visible(self):return True
    def press(self,key,**kwargs):
        self.events.append(key);self.page.text='ご依頼主を選択する';self.page.url=ORIGIN+'/sender'

class KeyboardBot(MenuBot):
    def __init__(self,page,blocked=False):super().__init__(page);self.keys=[];self.blocked=blocked
    def click(self,labels):
        self.clicks.append(labels)
        if self.blocked:raise UserError('overlay blocked click')
        return KeyboardTarget(self.page,self.keys)
    def wait_flow_stage(self,stages,timeout=15000):
        value=self.page.evaluate('stage')
        if value in stages:return value
        raise PagePollTimeout({'/menu':value})

class KeyboardTests(unittest.TestCase):
    def test_keyboard_fallback_once_after_completed_noop_mouse(self):
        bot=KeyboardBot(Page('/menu','マイページメインメニュー'))
        bot.enter_creation()
        self.assertEqual(bot.keys,['Enter'])
        self.assertEqual(len(bot.clicks),1)
    def test_does_not_keyboard_bypass_a_failed_mouse_click(self):
        bot=KeyboardBot(Page('/menu','マイページメインメニュー'),blocked=True)
        with self.assertRaises(UserError):bot.enter_creation()
        self.assertEqual(bot.keys,[])

class DiagnosticTests(unittest.TestCase):
    def test_report_omits_url_query_fragment_and_form_values(self):
        class DiagnosticPage:
            url=ORIGIN+'/mypage/M010100.do?session=DO_NOT_KEEP#private'
            def evaluate(self,script):return [{'tag':'IMG','alt':'送り状作成','action':{'kind':'javascript','commands':['create']}}]
        page=DiagnosticPage()
        with TemporaryDirectory() as directory:
            path=write_menu_diagnostic(page,Path(directory),RuntimeError('Timeout value="PRIVATE_FIELD" https://example.com/?secret=PRIVATE_TOKEN'),[page])
            content=path.read_text()
            self.assertNotIn('DO_NOT_KEEP',content)
            self.assertNotIn('PRIVATE_FIELD',content)
            self.assertNotIn('PRIVATE_TOKEN',content)
            self.assertEqual(json.loads(content)['controls'][0]['alt'],'送り状作成')

if __name__=='__main__':unittest.main()
