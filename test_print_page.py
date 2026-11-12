import unittest
from types import SimpleNamespace
from japanpost import Bot, ORIGIN

class Page:
    def __init__(self,stage,origin=ORIGIN): self.stage=stage;self.url=origin+'/page'
    def evaluate(self,script): return self.stage

class PrintBot(Bot):
    def __init__(self,main,pages): self.page=main;self.context=SimpleNamespace(pages=pages);self.pdfs=[]
    def collect_pdf(self): pass

class PrintPageTests(unittest.TestCase):
    def test_finds_print_popup_instead_of_staying_on_menu(self):
        main=Page('menu');popup=Page('print_notice')
        bot=PrintBot(main,[main,popup])
        self.assertEqual(bot.locate_print_page(timeout=0),'print_notice')
        self.assertIs(bot.page,popup)
    def test_menu_after_register_is_reported_not_created_again(self):
        main=Page('menu');bot=PrintBot(main,[main])
        self.assertEqual(bot.locate_print_page(timeout=0),'menu')
    def test_external_popup_not_used(self):
        main=Page('menu');popup=Page('print_notice','https://example.com')
        bot=PrintBot(main,[main,popup])
        self.assertEqual(bot.locate_print_page(timeout=0),'menu')
        self.assertIs(bot.page,main)

if __name__=='__main__':unittest.main()

class PrintClickBot(PrintBot):
    def __init__(self,main,pages):super().__init__(main,pages);self.clicks=[]
    def click(self,labels):self.clicks.append(labels)
    def collect_pdf(self):raise AssertionError('must not collect PDF after requested print stop')

class PrintEndpointTests(unittest.TestCase):
    def test_exact_official_button_is_clicked_once_then_returns(self):
        page=Page('print_notice');bot=PrintClickBot(page,[page])
        self.assertEqual(bot.finish_printing(),'print_clicked')
        self.assertEqual(len(bot.clicks),1)
        self.assertEqual(bot.clicks[0][0],'注意事項に同意して送り状を印刷')
        self.assertFalse(bot.printing_enabled)
    def test_repeated_print_click_is_rejected(self):
        page=Page('print_notice');bot=PrintClickBot(page,[page])
        bot.click_official_print()
        from japanpost import UserError
        with self.assertRaises(UserError):bot.click_official_print()
        self.assertEqual(len(bot.clicks),1)
    def test_preview_already_open_requires_no_extra_click(self):
        page=Page('print_preview');bot=PrintClickBot(page,[page])
        self.assertEqual(bot.finish_printing(),'print_preview')
        self.assertEqual(bot.clicks,[])
