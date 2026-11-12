"""Minimal action diagnostics; never read request bodies, headers or form values."""
import re
from urllib.parse import urlsplit


class ActionAudit:
    def __init__(self, page, secrets=()):
        self.page = page
        self.secrets = [s for s in secrets if s]
        self.posts, self.errors, self.dialogs, self.listeners = [], [], [], []

    def clean(self, text):
        text = str(text)
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, '[redacted]')
        text = re.sub(r'https?://[^\s]+', '[website URL]', text)
        return text.replace('\n', ' ')[:180]

    def on_request(self, request):
        parsed = urlsplit(request.url)
        if parsed.hostname in {'www.int-mypage.post.japanpost.jp', 'int-mypage.post.japanpost.jp'} and request.method.upper() == 'POST':
            self.posts.append(parsed.path.split(';')[0])

    def on_error(self, error):
        self.errors.append(self.clean(error))

    def on_dialog(self, dialog):
        self.dialogs.append(self.clean(dialog.message))
        # Match Playwright's normal dismiss behavior; do not auto-accept agreements.
        dialog.dismiss()

    def __enter__(self):
        for event, callback in [('request', self.on_request), ('pageerror', self.on_error), ('dialog', self.on_dialog)]:
            try:
                self.page.on(event, callback)
                self.listeners.append((event, callback))
            except AttributeError:
                pass
        return self

    def __exit__(self, *args):
        for event, callback in self.listeners:
            try:
                self.page.remove_listener(event, callback)
            except Exception:
                pass
        self.secrets.clear()

    def summary(self, unknown_if_empty=True):
        lines = ['Observed website POST requests: ' + str(len(self.posts)) + ' requests.']
        lines += ['Website dialog: ' + text for text in self.dialogs[-2:]]
        lines += ['Website script error: ' + text for text in self.errors[-2:]]
        if unknown_if_empty and not self.posts and not self.errors and not self.dialogs:
            lines.append('No submission request or page error observed; the reason for the ineffective click is unknown.')
        return '\n'.join(lines)
