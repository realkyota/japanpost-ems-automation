"""Body-safe stage detection; URLs are compared by pathname, never query strings."""
from urllib.parse import urlsplit
import time

READ_STAGE = r"""() => {
    if (!document.body) return 'loading';
    const images=[...document.querySelectorAll('img[alt],input[type="image"][alt]')].filter(e=>e.getClientRects().length).map(e=>e.getAttribute('alt')||'').join(' ');
    const text=((document.body.innerText || '')+' '+images).replace(/\s/g,'');
    if (text.includes('前回のデータから作成') && text.includes('新しく作成する')) return 'resume_prompt';
    if (text.includes('注意事項に同意して送り状を印刷') || text.includes('注意事項に同意して印刷')) return 'print_notice';
    if (location.pathname === '/mypage/M061000.do' && (text.includes('送り状の登録が完了しました') || text.includes('送り状の印刷をする'))) return 'print_notice';
    if (document.querySelector && document.querySelector('embed[type="application/pdf"],object[type="application/pdf"],iframe[src*=".pdf"]')) return 'print_preview';
    if (text.includes('マイページメインメニュー')) return 'menu';
    if (text.includes('登録内容をご確認ください')) return 'confirmation';
    if (text.includes('ご依頼主を選択する')) return 'sender';
    if (text.includes('お届け先を選択する')) return 'recipient_selection';
    if (text.includes('内容品を登録する') || (text.includes('発送種別の選択') && text.includes('EMS'))) return 'contents';
    if (text.includes('発送関連情報登録') || (text.includes('発送予定日') && text.includes('インボイス印刷指定'))) return 'dispatch';
    if (location.pathname === '/mypage/M060400.do') return 'recipient_form';
    return 'unknown';
}"""


def path_matches(url, path):
    return urlsplit(str(url)).path == path


class PagePollTimeout(TimeoutError):
    def __init__(self, last):
        super().__init__('Timed out waiting for page state')
        self.last = last


def poll_evaluate(page, expression, accepted, timeout=15000):
    """Explicit timer polling works even when browser animation frames are suspended."""
    deadline = time.monotonic() + timeout / 1000
    last = None
    while True:
        try:
            last = page.evaluate(expression)
        except Exception as error:
            last = {'evaluationError': type(error).__name__}
        if accepted(last):
            return last
        if time.monotonic() >= deadline:
            raise PagePollTimeout(last)
        page.wait_for_timeout(200)


def wait_stage(page, stages, timeout=15000):
    return poll_evaluate(page, READ_STAGE, lambda value: isinstance(value,str) and value in stages, timeout)
