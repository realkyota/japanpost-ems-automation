import unittest
from japanpost import Bot, ORIGIN, UserError

class Body:
    def __init__(self, text): self.text = text
    def inner_text(self): return self.text

class Page:
    def __init__(self, path, text): self.url = ORIGIN + path; self.text = text
    def wait_for_function(self, *args, **kwargs): pass
    def locator(self, selector): return Body(self.text)
    def evaluate(self, script):
        if self.url.endswith('/mypage/M060400.do'): return 'recipient_form'
        text=''.join(self.text.split())
        if '前回のデータから作成' in text and '新しく作成する' in text: return 'resume_prompt'
        if 'マイページメインメニュー' in text: return 'menu'
        if 'ご依頼主を選択する' in text: return 'sender'
        return 'unknown'
    def wait_for_timeout(self, timeout): raise TimeoutError('simulated deadline')

class MenuBot(Bot):
    def __init__(self, page): self.page = page; self.clicks = []
    def click(self, labels): self.clicks.append(labels); self.page.url = ORIGIN + '/sender-selection'; self.page.text='ご依頼主を選択する'
    def wait_ready(self): pass
    def manual_recovery(self, message): raise UserError(message)

class MenuTests(unittest.TestCase):
    def test_menu_clicks_creation_once(self):
        bot = MenuBot(Page('/menu', 'マイページ メインメニュー'))
        self.assertFalse(bot.enter_creation())
        self.assertEqual(bot.clicks, [['送り状作成', '送り状を作成する']])
    def test_already_on_recipient_skips_click(self):
        bot = MenuBot(Page('/mypage/M060400.do', 'お届け先情報の入力'))
        self.assertTrue(bot.enter_creation())
        self.assertFalse(bot.clicks)
    def test_unrecognized_login_result_never_clicks(self):
        bot = MenuBot(Page('/mypage/M010000.do', 'ログインできません'))
        with self.assertRaises(UserError): bot.enter_creation()
        self.assertFalse(bot.clicks)

if __name__ == '__main__': unittest.main()

class NavigationPage(Page):
    def evaluate(self, script): return {'ok': True}
    def locator(self, selector):
        if selector.startswith('[data-jp-ems-sender-next'):
            page = self
            class Next:
                def locator(self, selector):
                    class Empty:
                        def count(self): return 0
                    return Empty()
                def click(self, **kwargs): page.text = 'お届け先を選択する'; page.url = ORIGIN + '/recipient-selection'
            return Next()
        return Body(self.text)
    def wait_for_url(self, *args, **kwargs):
        if not self.url.endswith('/mypage/M060400.do'): raise AssertionError('wrong final page')

class NavigationBot(MenuBot):
    def load_helpers(self): pass
    def click(self, labels):
        self.clicks.append(labels)
        self.page.url = ORIGIN + '/mypage/M060400.do'

class RecipientNavigationTests(unittest.TestCase):
    def test_keeps_sender_then_opens_direct_entry(self):
        bot = NavigationBot(NavigationPage('/sender', 'ご依頼主を選択する'))
        self.assertTrue(bot.enter_recipient_form())
        self.assertEqual(bot.clicks, [['お届け先の入力']])
    def test_recipient_selection_opens_direct_entry(self):
        bot = NavigationBot(NavigationPage('/recipient-selection', 'お届け先を選択する'))
        self.assertTrue(bot.enter_recipient_form())
        self.assertEqual(bot.clicks, [['お届け先の入力']])
    def test_unknown_page_does_not_choose_saved_recipient(self):
        bot = NavigationBot(NavigationPage('/other', 'unknown'))
        self.assertFalse(bot.enter_recipient_form())
        self.assertFalse(bot.clicks)

class DraftPromptTests(unittest.TestCase):
    def test_existing_prompt_chooses_new_only(self):
        bot=MenuBot(Page('/menu','マイページメインメニュー 前回のデータから作成 新しく作成する'))
        bot.enter_creation()
        self.assertEqual(bot.clicks,[['新しく作成する']])
    def test_prompt_after_creation_chooses_new(self):
        class BotWithPrompt(MenuBot):
            def click(self,labels):
                if labels[0]=='送り状作成':
                    self.clicks.append(labels)
                    self.page.text='マイページメインメニュー 前回のデータから作成 新しく作成する'
                else: super().click(labels)
        bot=BotWithPrompt(Page('/menu','マイページメインメニュー'))
        bot.enter_creation()
        self.assertEqual(bot.clicks,[['送り状作成','送り状を作成する'],['新しく作成する']])
    def test_prompt_appearing_during_menu_click_is_handled(self):
        class BotWithRace(MenuBot):
            def click(self,labels):
                if labels[0]=='送り状作成':
                    self.clicks.append(labels)
                    self.page.text='マイページメインメニュー 前回のデータから作成 新しく作成する'
                    raise UserError('menu covered by newly appeared modal')
                super().click(labels)
        bot=BotWithRace(Page('/menu','マイページメインメニュー'))
        bot.enter_creation()
        self.assertEqual(bot.clicks,[['送り状作成','送り状を作成する'],['新しく作成する']])
    def test_new_draft_never_retried_implicitly(self):
        bot=MenuBot(Page('/menu','前回のデータから作成 新しく作成する'))
        bot._new_draft_clicked=True
        with self.assertRaises(UserError): bot.choose_new_draft()
        self.assertEqual(bot.clicks,[])

class NewDraftReturnsMenuTests(unittest.TestCase):
    def test_initial_new_draft_returns_menu_then_create(self):
        class ReturnToMenu(MenuBot):
            def click(self,labels):
                if labels==['新しく作成する']:
                    self.clicks.append(labels);self.page.text='マイページメインメニュー';return
                super().click(labels)
        bot=ReturnToMenu(Page('/menu','マイページメインメニュー 前回のデータから作成 新しく作成する'))
        bot.enter_creation()
        self.assertEqual(bot.clicks,[['新しく作成する'],['送り状作成','送り状を作成する']])
    def test_menu_prompt_discard_returns_menu_then_create_again(self):
        class ReturnToMenu(MenuBot):
            def __init__(self,page): super().__init__(page);self.cleared=False
            def click(self,labels):
                if labels==['新しく作成する']:
                    self.clicks.append(labels);self.cleared=True;self.page.text='マイページメインメニュー';return
                if not self.cleared:
                    self.clicks.append(labels);self.page.text='マイページメインメニュー 前回のデータから作成 新しく作成する';return
                super().click(labels)
        bot=ReturnToMenu(Page('/menu','マイページメインメニュー'))
        bot.enter_creation()
        self.assertEqual(bot.clicks,[['送り状作成','送り状を作成する'],['新しく作成する'],['送り状作成','送り状を作成する']])
