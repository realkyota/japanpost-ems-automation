import json
import shutil
import subprocess
import unittest
from page_state import READ_STAGE, path_matches, wait_stage
from page_state import poll_evaluate, PagePollTimeout
from unittest.mock import patch


class PageStateTests(unittest.TestCase):
    def test_path_matches_with_locale_query_and_fragment(self):
        for suffix in ['', '?request_locale=ja', '?request_locale=ja&x=1#top']:
            self.assertTrue(path_matches('https://www.int-mypage.post.japanpost.jp/mypage/M060800.do'+suffix, '/mypage/M060800.do'))
        self.assertFalse(path_matches('https://example.com/mypage/M060400.do', '/mypage/M060800.do'))

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for offline JS predicate checks')
    def test_actual_stage_predicate_handles_missing_body_and_newlines(self):
        fixtures=[
            {'body':None,'path':'/mypage/M010100.do','expected':'loading'},
            {'body':'マイページ\nメインメニュー','path':'/mypage/M010100.do','expected':'menu'},
            {'body':'マイページメインメニュー 前回のデータから作成 新しく作成する','path':'/mypage/M010100.do','expected':'resume_prompt'},
            {'body':'ご依頼主を選択する','path':'/sender','expected':'sender'},
            {'body':'','images':['ご依頼主を選択する'],'path':'/sender','expected':'sender'},
            {'body':'お届け先を選択する','path':'/select','expected':'recipient_selection'},
            {'body':'内容品を登録する','path':'/mypage/M060800.do','expected':'contents'},
            {'body':'発送種別の選択 EMS','path':'/other-content-path','expected':'contents'},
            {'body':'発送予定日 インボイス印刷指定','path':'/dispatch','expected':'dispatch'},
            {'body':'登録内容をご確認ください','path':'/confirmation','expected':'confirmation'},
            {'body':'注意事項に同意して送り状を印刷','path':'/mypage/M061000.do','expected':'print_notice'},
            {'body':'送り状の登録が完了しました','path':'/mypage/M061000.do','expected':'print_notice'},
            {'body':'','path':'/other','expected':'unknown'},
        ]
        script="""const fs=require('node:fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));
        const run=new Function('document','location','return ('+data.source+')()');
        const actual=data.fixtures.map(f=>run({body:f.body===null?null:{innerText:f.body},querySelectorAll:()=>(f.images||[]).map(text=>({getClientRects:()=>[1],getAttribute:()=>text}))},{pathname:f.path}));
        process.stdout.write(JSON.stringify(actual));"""
        result=subprocess.run(['node','-e',script],input=json.dumps({'source':READ_STAGE,'fixtures':fixtures}),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),[f['expected'] for f in fixtures])

    def test_wait_stage_uses_explicit_evaluation_not_animation_frames(self):
        class Page:
            def evaluate(self, expression): self.expression=expression;return 'contents'
            def wait_for_function(self, *args, **kwargs): raise AssertionError('RAF polling must not be used')
        page=Page();wait_stage(page,['contents'])
        self.assertIn('if (!document.body)',page.expression)

    def test_poll_recovers_from_navigation_and_returns_result(self):
        class Page:
            def __init__(self): self.calls=0;self.intervals=[]
            def evaluate(self, expression):
                self.calls+=1
                if self.calls==1: raise RuntimeError('execution context changed')
                return {'ok':self.calls>=3}
            def wait_for_timeout(self, interval): self.intervals.append(interval)
            def wait_for_function(self, *args, **kwargs): raise AssertionError('must not use RAF')
        page=Page()
        result=poll_evaluate(page,'example()',lambda value:isinstance(value,dict) and value.get('ok') is True)
        self.assertEqual(result,{'ok':True})
        self.assertEqual(page.intervals,[200,200])

    def test_timeout_keeps_last_field_diagnostic(self):
        class Page:
            def evaluate(self, expression): return {'ok':False,'message':'HS code not identified'}
            def wait_for_timeout(self, interval): pass
        with patch('page_state.time.monotonic',side_effect=[0,0.1,1]):
            with self.assertRaises(PagePollTimeout) as error:
                poll_evaluate(Page(),'example()',lambda value:value.get('ok') is True,timeout=500)
        self.assertEqual(error.exception.last['message'],'HS code not identified')


if __name__=='__main__': unittest.main()
