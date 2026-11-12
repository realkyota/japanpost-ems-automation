#!/usr/bin/env python3
"""Local Japan Post EMS browser automation. No embedded account credentials."""
from __future__ import annotations

import argparse
from copy import deepcopy
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4
from credentials import load_saved, setup_login, forget_login
from action_audit import ActionAudit
from page_state import READ_STAGE, path_matches, wait_stage, poll_evaluate, PagePollTimeout
from diagnostics import write_menu_diagnostic, DiagnosticJournal, reveal_report

ROOT = Path(__file__).resolve().parent
ORIGIN = 'https://www.int-mypage.post.japanpost.jp'
LOGIN = ORIGIN + '/mypage/M010000.do'
BUILD = '20261112-always-write-diagnostic-1'
JST = timezone(timedelta(hours=9))
RECIPIENT = '/mypage/M060400.do'
CONTENTS = '/mypage/M060800.do'


class UserError(Exception):
    pass


def validate(data):
    if not isinstance(data, dict):
        raise UserError('Input must be a JSON object.')
    if set(data) - {'recipient', 'shipment', '_example'}:
        raise UserError('Only recipient, shipment and _example are supported at the top level.')
    if data.get('_example', False) is not False:
        raise UserError('Example data cannot create labels. Supply real data and remove _example.')
    recipient, shipment = data.get('recipient'), data.get('shipment')
    if not isinstance(recipient, dict) or not isinstance(shipment, dict):
        raise UserError('Missing recipient or shipment object.')
    keys = {'name', 'country', 'address1', 'address2', 'city', 'state', 'postalCode', 'phone', 'fax', 'email'}
    if set(recipient) - keys:
        raise UserError('Unsupported recipient field.')
    for key in keys:
        value = recipient.get(key, '')
        if not isinstance(value, str) or re.search(r'[\x00-\x1f]', value):
            raise UserError(f'recipient.{key} must be a string without line breaks.')
    for key in ['name', 'country', 'address2', 'city']:
        if not recipient.get(key, '').strip():
            raise UserError(f'Missing recipient.{key}。')
    if not re.fullmatch('[A-Z]{2}', recipient['country']):
        raise UserError('country must be a two-letter uppercase country/region code.')
    if recipient.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', recipient['email']):
        raise UserError('Invalid recipient email address.')
    allowed = {'item', 'category', 'paid', 'invoice', 'noDangerousGoods', 'shipDate', 'totalWeightGrams', 'insuredValueYen'}
    if set(shipment) - allowed:
        raise UserError('Unsupported shipment field.')
    if shipment.get('noDangerousGoods') is not True:
        raise UserError('Confirm the contents contain no dangerous goods, then set noDangerousGoods:true.')
    if type(shipment.get('paid')) is not bool:
        raise UserError('paid must explicitly be true (sale) or false (unpaid).')
    if not isinstance(shipment.get('category'), str) or not shipment['category']:
        raise UserError('Supply category using the label displayed on the website.')
    if shipment['category'] == '贈物' and shipment['paid']:
        raise UserError('Gift category conflicts with paid:true.')
    if shipment.get('invoice') != 'prescribed':
        raise UserError('invoice must be prescribed (required number of copies).')
    if 'shipDate' in shipment:
        try:
            if not re.fullmatch(r'\d{4}/\d{2}/\d{2}', shipment['shipDate']):
                raise ValueError()
            datetime.strptime(shipment['shipDate'], '%Y/%m/%d')
        except (ValueError, TypeError):
            raise UserError('shipDate must be a valid date in YYYY/MM/DD format.') from None
    item = shipment.get('item')
    if not isinstance(item, dict) or set(item) - {'name', 'unitPrice', 'quantity', 'weightGrams', 'origin', 'hsCode'}:
        raise UserError('Supply exactly one item object.')
    # Public edition: shipping declarations must come from the input file.
    if not isinstance(item.get('origin'), str) or not re.fullmatch('[A-Z]{2}', item['origin']):
        raise UserError('Explicitly supply item.origin as a two-letter country code.')
    for key in ['name', 'unitPrice', 'quantity']:
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise UserError(f'Missing string item.{key}。')
    if not re.fullmatch(r'[\x20-\x7e]+', item['name']):
        raise UserError('Item name must use printable ASCII characters.')
    if not re.fullmatch(r'\d+(\.\d{1,2})?', item['unitPrice']):
        raise UserError('unitPrice must be a numeric string in JPY.')
    if not re.fullmatch(r'[1-9]\d*', item['quantity']):
        raise UserError('quantity must be a positive integer string.')
    for obj, key in [(item, 'weightGrams'), (shipment, 'totalWeightGrams'), (shipment, 'insuredValueYen')]:
        if key in obj and (not isinstance(obj[key], str) or not re.fullmatch(r'\d+', obj[key])):
            raise UserError(f'{key} must be a nonnegative integer string.')
    if item.get('origin') is not None and (not isinstance(item['origin'], str) or not re.fullmatch('[A-Z]{2}', item['origin'])):
        raise UserError('item.origin must be a two-letter uppercase country code.')
    if item.get('hsCode') is not None and (not isinstance(item['hsCode'], str) or not re.fullmatch(r'\d{6,10}', item['hsCode'])):
        raise UserError('hsCode must be a string of 6 to 10 digits.')
    if item.get('weightGrams') and shipment.get('totalWeightGrams'):
        if int(item['weightGrams']) * int(item['quantity']) > int(shipment['totalWeightGrams']):
            raise UserError('Total parcel weight is less than the combined item weight.')
    return data


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def with_next_day(data, started_at):
    if started_at.tzinfo is None:
        raise UserError('Startup time must include a timezone.')
    result = deepcopy(data)
    result['shipment']['shipDate'] = (started_at.astimezone(JST).date() + timedelta(days=1)).strftime('%Y/%m/%d')
    return result


def country_option(options, code):
    def norm(value):
        return re.sub(r'[\s()（）]', '', unicodedata.normalize('NFKC', value)).upper()
    aliases = {'JP': {'JP', 'JAPAN', '日本', 'JAPAN日本', '日本JAPAN'}}
    names = aliases.get(code, {code})
    matches = [o['value'] for o in options if o.get('value') and not o.get('disabled') and (norm(o['value']) == code or norm(o['label']) in names)]
    if len(matches) != 1:
        raise UserError('Cannot uniquely match the origin dropdown option: ' + code)
    return matches[0]


class Ledger:
    """Only hashes/status are saved. Never retry registration implicitly."""
    def __init__(self, directory):
        self.path = directory / 'run-state.json'
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}

    def check(self, key, allow_repeat=False):
        if key in self.records and not allow_repeat:
            when = self.records[key].get('time', 'unknown time')
            raise UserError('Duplicate protection: registration was already attempted for this input ('+when+'). Check the official 「発送予定データ」 before retrying. Use --allow-repeat only when you intend to create another label. Preserve run-state.json.')

    def attempted(self, key):
        self.records[key] = {'status': 'registration_attempted', 'time': datetime.now(JST).isoformat()}
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.records, indent=2))
        os.chmod(temp, 0o600)
        temp.replace(self.path)


def choose_file():
    if sys.platform != 'darwin':
        raise UserError('Specify a JSON file on the command line.')
    result = subprocess.run(['osascript', '-e', 'POSIX path of (choose file with prompt "Select recipient and shipment JSON file")'], capture_output=True, text=True)
    if result.returncode:
        raise UserError('No input file selected.')
    return Path(result.stdout.strip())


class Bot:
    def __init__(self, page, data, output, context):
        self.page, self.data, self.output, self.context = page, data, output, context
        self.pdfs = []
        self.seen_pdf = set()
        self.printing_enabled = False
        self.pending_responses = []
        self.pending_downloads = []
        context.on('response', self.queue_response)
        context.on('page', self.watch_page)
        self.watch_page(page)

    def queue_response(self, response):
        if self.printing_enabled and urlparse(response.url).hostname == urlparse(ORIGIN).hostname:
            if ('application/pdf' in response.headers.get('content-type', '').lower()
                    or '.pdf' in response.headers.get('content-disposition', '').lower()):
                self.pending_responses.append(response)

    def watch_page(self, page):
        page.on('download', lambda download: self.pending_downloads.append(download) if self.printing_enabled else None)

    def save_pdf(self, content):
        if not content.startswith(b'%PDF-'):
            return
        digest = hashlib.sha256(content).hexdigest()
        if digest in self.seen_pdf:
            return
        path = self.output / ('label-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:6] + '.pdf')
        path.write_bytes(content)
        os.chmod(path, 0o600)
        self.seen_pdf.add(digest)
        self.pdfs.append(path)
        print('Saved official PDF: ', path)

    def collect_pdf(self):
        # Called outside event callbacks so page actions are not blocked by PDF reads.
        for response in self.pending_responses[:]:
            try:
                self.save_pdf(response.body())
            except Exception:
                pass
            self.pending_responses.remove(response)
        for download in self.pending_downloads[:]:
            try:
                if (urlparse(download.url).hostname != urlparse(ORIGIN).hostname
                        and not download.url.startswith('blob:' + ORIGIN + '/')):
                    continue
                temp = self.output / ('.download-' + uuid4().hex)
                try:
                    download.save_as(temp)
                    self.save_pdf(temp.read_bytes())
                finally:
                    temp.unlink(missing_ok=True)
            except Exception:
                pass
            finally:
                self.pending_downloads.remove(download)

    def load_helpers(self):
        if urlparse(self.page.url).hostname != urlparse(ORIGIN).hostname:
            raise UserError('The current page is not on the official Japan Post website.')
        for name in ['recipient.js', 'shipment.js', 'login.js', 'navigation.js', 'content.js']:
            self.page.add_script_tag(content=(ROOT / name).read_text())

    def operate(self, action):
        if action == 'register':
            self.click(['送り状を登録する'])
            return
        self.load_helpers()
        result = self.page.evaluate('args => operateShipment(args.data, args.action)', {'data': self.data['shipment'], 'action': action})
        if not result.get('ok'):
            raise UserError(result.get('message', 'Website action failed.'))

    def click_control(self, locator):
        images = locator.locator('img,input[type="image"]')
        visible = [images.nth(i) for i in range(images.count()) if images.nth(i).is_visible()]
        if len(visible) > 1:
            raise UserError('Multiple visible images inside the control; stopped to avoid clicking the wrong target.')
        target = visible[0] if visible else locator
        try:
            self.page.bring_to_front()
        except Exception:
            pass
        target.click(timeout=15000)
        return target

    def click(self, labels):
        self.load_helpers()
        # Image-first: legacy image anchors can have a different hit area than the image.
        for label in labels:
            for role in ['img', 'button', 'link']:
                locator = self.page.get_by_role(role, name=label, exact=True)
                visible = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
                if len(visible) == 1:
                    return self.click_control(visible[0])
        raise UserError('Cannot uniquely identify control: ' + '/'.join(labels))

    def wait_ready(self):
        try:
            self.page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(400)

    def manual_recovery(self, message):
        if getattr(self,'journal',None):
            self.journal.event('paused',message=message[:240])
        print('\nPaused: ' + message)
        input('Complete or correct the current step in the browser, then press Enter here to resume (Ctrl+C to exit): ')

    def step(self, title, operation):
        self.current_step = title
        if getattr(self,'journal',None):
            self.journal.event(title)
        print('→ ' + title)
        try:
            operation()
        except UserError as error:
            self.manual_recovery(str(error))
        self.wait_ready()

    def fill_recipient(self):
        self.load_helpers()
        recipient = self.page.evaluate('text => parseRecipient(text)', json.dumps(self.data['recipient'], ensure_ascii=False))
        result = self.page.evaluate('data => fillJapanPost(data)', recipient)
        if not result.get('ok'):
            raise UserError(result['message'])

    def login(self, credentials):
        with ActionAudit(self.page, credentials.values()) as audit:
            result = self._login(credentials)
            print(audit.summary(unknown_if_empty=not result.get('ok')))
            return result

    def _login(self, credentials):
        try:
            self.page.wait_for_load_state('load', timeout=15000)
            poll_evaluate(self.page, 'typeof submitCommand === "function" && typeof setValue === "function" && typeof mailSave === "function"', lambda value: value is True, timeout=10000)
        except Exception:
            return {'ok': False, 'message': 'The website login script is not ready. No login attempted; check page loading.'}
        self.load_helpers()
        result = self.page.evaluate('data => loginJapanPost(data, true)', credentials)
        if not result.get('ok'):
            return result
        try:
            # Native Playwright input/mouse actions trigger focus, pointer and blur events.
            self.page.locator('[data-jp-login-user="true"]').fill(credentials['username'])
            self.page.locator('[data-jp-login-password="true"]').fill(credentials['password'])
            self.page.locator('[data-jp-login-password="true"]').press('Tab')
            self.page.locator('[data-jp-login-button="true"]').click(timeout=15000)
        except Exception:
            return {'ok': False, 'message': 'Login input or click did not complete. Check for overlays, verification or errors. No automatic retry.'}
        print('→ Clicked the login image; waiting for the website response')
        try:
            wait_stage(self.page, ['menu', 'resume_prompt'], timeout=20000)
        except Exception:
            return {'ok': False, 'message': 'Clicked 「ログイン」 but the main menu was not detected. Check credentials, verification and website messages.'}
        return {'ok': True, 'message': 'Detected the signed-in main menu.'}

    def enter_creation(self):
        if getattr(self,'journal',None):self.journal.event('opening_label_creation')
        self._new_draft_clicked = False
        self._keyboard_menu_attempted = False
        self._menu_activation_log = []
        print('→ Waiting for the signed-in Japanese main menu')
        destinations = ['sender', 'recipient_selection', 'recipient_form']
        try:
            self.wait_flow_stage(['menu', 'resume_prompt'] + destinations)
        except Exception:
            self.manual_recovery('Complete login/verification, select Japanese, and leave the main menu or sender selection page open.')
        menu_clicks = 0
        with ActionAudit(self.page) as audit:
            try:
                while True:
                    stage = self.page.evaluate(READ_STAGE)
                    if stage in destinations:
                        return stage == 'recipient_form'
                    if stage == 'resume_prompt':
                        self.choose_new_draft()
                        continue
                    if stage != 'menu':
                        raise UserError('Unrecognized menu or creation stage: ' + str(stage))
                    if menu_clicks >= 2:
                        raise UserError('Main menu clicked twice; no further automatic retries.')
                    menu_clicks += 1
                    print('→ Clicking 「送り状作成」 on the main menu')
                    if getattr(self,'journal',None):
                        self.journal.event('clicking_main_menu',attempt=menu_clicks)
                        try:
                            write_menu_diagnostic(self.page,self.output,None,getattr(getattr(self,'context',None),'pages',[]),self._menu_activation_log)
                        except Exception:
                            pass
                    control = None
                    mouse_completed = False
                    posts_before = len(audit.posts)
                    try:
                        control = self.click(['送り状作成', '送り状を作成する'])
                        mouse_completed = True
                        self._menu_activation_log.append({'method':'mouse','completed':True})
                        self.wait_flow_stage(destinations + ['resume_prompt'])
                    except Exception:
                        if not self._new_draft_clicked and self.page.evaluate(READ_STAGE) == 'resume_prompt':
                            continue
                        if (mouse_completed and control is not None and len(audit.posts)==posts_before
                                and self.page.evaluate(READ_STAGE)=='menu' and not self._keyboard_menu_attempted):
                            self._keyboard_menu_attempted = True
                            if self.keyboard_activate_menu(control):
                                self._menu_activation_log.append({'method':'keyboard_enter','completed':True})
                                self.wait_flow_stage(destinations + ['resume_prompt'])
                                continue
                        raise
            except Exception as error:
                print(audit.summary())
                print('Main menu action did not complete: ' + type(error).__name__)
                try:
                    path=write_menu_diagnostic(self.page,self.output,error,getattr(getattr(self,'context',None),'pages',[]),self._menu_activation_log)
                    print('Saved control diagnostics: ' + str(path))
                    reveal_report(path)
                except Exception as diagnostic_error:
                    print('Could not save diagnostics: '+type(diagnostic_error).__name__+'; expected location: '+str(getattr(self,'output',ROOT/'output')/'diagnostic-main-menu.json'))
                self.manual_recovery('Creation flow not reached. Choose 「新しく作成する」 if prompted; if returned to the main menu, click 「送り状作成」 again. Resume on sender selection.')
        self.wait_ready()
        stage = self.page.evaluate(READ_STAGE)
        if stage not in destinations:
            raise UserError('Sender/recipient selection not reached; label creation has not started.')
        return stage == 'recipient_form'

    def choose_new_draft(self):
        if self.page.evaluate(READ_STAGE) != 'resume_prompt':
            return False
        if self._new_draft_clicked:
            raise UserError('New draft already attempted; no repeated click. Check the website.')
        print('→ Previous-draft prompt detected; clicking 「新しく作成する」')
        self._new_draft_clicked = True
        self.click(['新しく作成する'])
        # Discarding the previous draft may return to the menu, rather than start it.
        result = self.wait_flow_stage(['menu', 'sender', 'recipient_selection', 'recipient_form'])
        if result == 'menu':
            print('→ Returned to the main menu after resetting the draft; clicking 「送り状作成」 again')
        return True

    def wait_flow_stage(self, stages, timeout=15000):
        deadline=time.monotonic()+timeout/1000
        last={}
        while True:
            pages=list(getattr(getattr(self,'context',None),'pages',[]))
            if self.page not in pages: pages.append(self.page)
            for candidate in reversed(pages):
                try:
                    if urlparse(candidate.url).hostname not in {'www.int-mypage.post.japanpost.jp','int-mypage.post.japanpost.jp'}: continue
                    stage=candidate.evaluate(READ_STAGE)
                    last[urlparse(candidate.url).path]=stage
                    if isinstance(stage,str) and stage in stages:
                        if candidate is not self.page:
                            print('→ Website window detected; switching to the creation flow')
                            self.page=candidate
                        return stage
                except Exception:
                    continue
            if time.monotonic()>=deadline: raise PagePollTimeout(last)
            self.page.wait_for_timeout(200)

    def keyboard_activate_menu(self, control):
        anchors=control.locator('xpath=ancestor-or-self::a[1]')
        if anchors.count()==1 and anchors.nth(0).is_visible():
            target=anchors.nth(0)
        else:
            tag=control.evaluate('(e)=>e.tagName')
            if tag not in ['BUTTON','INPUT','A']: return False
            target=control
        print('→ Still on main menu with no POST observed; trying Enter once on the control')
        target.press('Enter',timeout=15000)
        return True

    def enter_recipient_form(self):
        if urlparse(self.page.url).path == RECIPIENT:
            return True
        self.wait_ready()
        text = re.sub(r'\s', '', self.page.locator('body').inner_text())
        if 'ご依頼主を選択する' in text:
            print('→ Keeping selected sender; clicking bottom workflow 「次へ」')
            self.load_helpers()
            result = self.page.evaluate('markSenderNext()')
            if not result.get('ok'):
                raise UserError(result.get('message', 'Cannot identify sender selection page.'))
            self.click_control(self.page.locator('[data-jp-ems-sender-next="true"]'))
            self.wait_ready()
            text = re.sub(r'\s', '', self.page.locator('body').inner_text())
        if urlparse(self.page.url).path == RECIPIENT:
            return True
        if 'お届け先を選択する' in text:
            print('→ Clicking 「お届け先の入力」 for the JSON recipient')
            self.click(['お届け先の入力'])
            self.page.wait_for_url(lambda url: path_matches(url, RECIPIENT), timeout=15000)
            return True
        return False

    def confirm_item(self):
        self.click(['確定'])
        self.wait_ready()
        # Check registered table content rather than trusting a click result.
        text = self.page.locator('body').inner_text()
        if self.data['shipment']['item']['name'] not in text:
            raise UserError('Registered item not confirmed; check website errors.')

    def wait_for_contents(self):
        try:
            wait_stage(self.page, ['contents'])
        except Exception:
            path = urlparse(self.page.url).path.split(';')[0]
            raise UserError('Contents page not detected. Current path: ' + path + '. If EMS options are visible, verify and resume; URL parameters do not require a new login.') from None

    def select_ems_goods(self):
        with ActionAudit(self.page) as audit:
            try:
                self._select_ems_goods()
            except UserError:
                print('EMS selection may only change page visibility; POST count does not establish selection.')
                print(audit.summary(unknown_if_empty=False))
                raise

    def _select_ems_goods(self):
        try:
            self.load_helpers()
            result = self.page.evaluate('markEMSContent()')
            if not result.get('ok'):
                raise UserError(result['message'])
            self.page.locator('[data-jp-content-service="true"]').click(timeout=15000)
            # Documents hide the item area. Wait for the goods inputs to actually appear.
            self.wait_ready()
            self.load_helpers()
            poll_evaluate(self.page, 'markContentInputs()', lambda value: isinstance(value,dict) and value.get('ok') is True, timeout=15000)
            print('→ Expanded item input area detected')
        except PagePollTimeout as error:
            reason = error.last.get('message', 'Field inspection has not returned a result') if isinstance(error.last,dict) else 'Field inspection has not returned a result'
            raise UserError('Input area detection after EMS click did not complete: ' + reason) from None
        except UserError:
            raise
        except Exception:
            raise UserError('The item input area was not detected after clicking EMS（物品）. Select EMS（物品） on the website and resume.') from None

    def fill_and_confirm_item(self):
        try:
            self.load_helpers()
            existing = self.page.evaluate('registeredContents()')
            if existing:
                raise UserError('An item is already registered; no duplicate added. Review/edit it on the website before resuming.')
            result = self.page.evaluate('markContentInputs()')
            if not result.get('ok'):
                raise UserError(result['message'])
            item = self.data['shipment']['item']
            def field(key):
                return self.page.locator('[data-jp-content-' + key + '="true"]')
            expected = {}
            for key in ['name', 'unitPrice', 'weightGrams', 'hsCode', 'quantity']:
                value = item.get(key, '')
                control = field(key)
                limit = control.get_attribute('maxlength')
                if limit and int(limit) >= 0 and len(value) > int(limit):
                    raise UserError('Item field exceeds the website length limit: ' + key)
                control.fill(value)
                expected[key] = value
            currency = field('currency').select_option(label='JPY/円')
            options = field('origin').locator('option').evaluate_all('(els)=>els.map(o=>({value:o.value,label:o.textContent,disabled:o.disabled}))')
            origin_value = country_option(options, item['origin'])
            field('origin').select_option(value=origin_value)
            field('quantity').press('Tab')
            if any(field(key).input_value() != value for key, value in expected.items()):
                raise UserError('Website did not retain all item values; 「確定」 not clicked.')
            if field('origin').input_value() != origin_value or field('currency').input_value() not in currency:
                raise UserError('Currency or origin selection was not retained; 「確定」 not clicked.')
            print('→ Item filled; clicking 「確定」 to add it')
            self.click_control(field('confirm'))
            self.wait_ready()
            self.load_helpers()
            rows = poll_evaluate(self.page, 'registeredContents()', lambda value: isinstance(value,list) and len(value)>0, timeout=15000)
            if len(rows) != 1 or rows[0]['name'] != item['name'] or rows[0]['quantity'] != item['quantity']:
                raise UserError('Cannot confirm exactly one registered item and its quantity. Check the website.')
        except UserError:
            raise
        except Exception:
            raise UserError('Item input, dropdown selection or 「確定」 did not complete. Check the page; no automatic duplicate addition.') from None

    def confirmation(self):
        wait_stage(self.page, ['confirmation'])
        text = self.page.locator('body').inner_text()
        expected = [self.data['recipient']['name'], self.data['shipment']['item']['name'], 'EMS']
        if not all(value in text for value in expected):
            raise UserError('Review page is missing the expected recipient, item or EMS. Automatic registration stopped.')

    def locate_print_page(self, timeout=5000):
        deadline = time.monotonic() + timeout / 1000
        current = 'unknown'
        while True:
            pages = list(self.context.pages)
            if self.page not in pages:
                pages.append(self.page)
            for candidate in reversed(pages):
                try:
                    if urlparse(candidate.url).hostname != urlparse(ORIGIN).hostname:
                        continue
                    stage = candidate.evaluate(READ_STAGE)
                    if candidate is self.page:
                        current = stage
                    if stage in ['print_notice', 'print_preview']:
                        self.page = candidate
                        return stage
                except Exception:
                    continue
            if time.monotonic() >= deadline:
                return current
            self.page.wait_for_timeout(200)

    def finish_printing(self):
        stage = self.locate_print_page()
        if stage not in ['print_notice', 'print_preview']:
            if stage == 'menu':
                self.manual_recovery('Returned to main menu after registration. Check 「発送予定データ」 and open that record’s print page; do not recreate it.')
            else:
                self.manual_recovery('Open the official label print page (M061000.do), then resume.')
            stage = self.locate_print_page()
        if stage == 'print_preview':
            print('Official PDF/print preview opened. Automation stopped.')
            return 'print_preview'
        if stage != 'print_notice':
            print('Print page not detected. Automation stopped; browser left open for manual handling.')
            return 'manual_print'
        return self.click_official_print()

    def click_official_print(self):
        if getattr(self, '_print_clicked', False):
            raise UserError('Official print button already attempted; no repeated click.')
        if self.page.evaluate(READ_STAGE) != 'print_notice':
            raise UserError('Not on the official print page; no click performed.')
        self.current_step = 'Click official print button and stop'
        self._print_clicked = True
        self.printing_enabled = False
        self.click(['注意事項に同意して送り状を印刷', '注意事項に同意して印刷', '注意事項に同意して印刷する'])
        print('Clicked 「注意事項に同意して送り状を印刷」. Automation stopped; browser remains open.')
        return 'print_clicked'

    def run(self, ledger, key, stop_before_register):
        self.step('Fill recipient', self.fill_recipient)
        self.step('Open contents page', lambda: self.click(['次へ']))
        self.step('Wait for contents page', lambda: self.wait_for_contents())
        self.step('Select EMS（物品） and wait for item inputs', self.select_ems_goods)
        self.step('Fill and confirm one item', self.fill_and_confirm_item)
        self.step('Set category and dangerous-goods declaration', lambda: self.operate('declaration'))
        self.step('Open dispatch page', lambda: self.click(['次へ']))
        self.step('Fill dispatch information', lambda: self.operate('dispatch'))
        self.step('Open registration review', lambda: self.click(['次へ']))
        self.confirmation()
        if stop_before_register:
            print('Stopped at review as requested; no registration performed.')
            return
        # Write before dispatch: no automatic re-submit if navigation or output fails.
        ledger.attempted(key)
        self.printing_enabled = False
        print('→ Registering the official shipping label (no automatic retry)')
        self.operate('register')
        self.wait_ready()
        return self.finish_printing()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local Japan Post EMS automation for macOS')
    parser.add_argument('file', nargs='?', type=Path, help='Recipient/shipment JSON; omit to open the macOS file picker')
    login_modes = parser.add_mutually_exclusive_group()
    login_modes.add_argument('--login', action='store_true', help='Enter credentials for this run only; password hidden and not saved')
    login_modes.add_argument('--setup-login', action='store_true', help='Save login credentials to macOS Keychain, then exit')
    login_modes.add_argument('--forget-login', action='store_true', help='Delete this application’s Keychain credentials, then exit')
    login_modes.add_argument('--manual-login', action='store_true', help='Ignore saved credentials and log in manually in the browser')
    parser.add_argument('--print', dest='print_pdf', action='store_true', help='Legacy option; only click the official print button and stop')
    parser.add_argument('--stop-before-register', action='store_true', help='Stop at review without registering')
    parser.add_argument('--allow-repeat', action='store_true', help='Allow repeated input after checking existing records on the website')
    parser.add_argument('--validate-only', action='store_true', help='Validate JSON only; do not open the browser')
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args(argv)
    started_at = datetime.now(JST)
    print('EMS build: ' + BUILD)
    try:
        if args.setup_login:
            setup_login()
            return 0
        if args.forget_login:
            forget_login()
            print('Deleted this application’s Keychain credentials.')
            return 0
    except RuntimeError as error:
        raise UserError(str(error)) from None
    output = args.output.resolve()
    try:
        journal = DiagnosticJournal(output, BUILD)
    except OSError as error:
        raise UserError('Cannot create diagnostic file: '+str(output/'diagnostic-main-menu.json')+'（'+type(error).__name__+'）') from None
    print('Diagnostic file path: ' + str(journal.path))
    try:
        return _run_main_flow(args, started_at, journal)
    except BaseException as error:
        details={'exceptionType':type(error).__name__}
        if isinstance(error,UserError):details['message']=str(error)[:600]
        journal.event('exit_exception',**details)
        reveal_report(journal.path)
        raise


def _run_main_flow(args, started_at, journal):
    path = args.file or choose_file()
    data = validate(json.loads(path.read_text(encoding='utf-8-sig')))
    journal.event('configuration_validated')
    # Keep duplicate protection based on the input, not an automatically changing day.
    key = fingerprint(data)
    data = with_next_day(data, started_at)
    print('Dispatch date: ' + data['shipment']['shipDate'] + ' (day after startup in Japan time)')
    if args.validate_only:
        print('Input format validated. Destination rules, HS classification and website fields have not been checked.')
        return 0
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(output)
    if not args.stop_before_register:
        journal.event('checking_duplicate_record')
        ledger.check(key, args.allow_repeat)
    credentials = None
    if args.login:
        credentials = {'username': input('Japan Post login email / ID: ').strip(), 'password': getpass.getpass('Password (hidden; not saved): ')}
    elif not args.manual_login and sys.platform == 'darwin':
        try:
            credentials = load_saved()
            if credentials is None:
                print('No saved credentials. Log in manually, or run setup_login.command to configure automatic login.')
        except RuntimeError as error:
            print(str(error))
            print('Using manual browser login for this run.')
    if args.print_pdf:
        print('This version only clicks the website print button; it does not send system print jobs.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise UserError('Missing dependencies. Run bash run.command or install requirements.txt.') from None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True, locale='ja-JP')
        page = context.new_page()
        bot = Bot(page, data, output, context)
        bot.journal = journal
        try:
            journal.event('opening_login_page')
            page.goto(LOGIN, wait_until='domcontentloaded')
            if credentials:
                try:
                    print('→ Filling credentials and attempting Japan Post login')
                    result = bot.login(credentials)
                    print(result.get('message', 'Check the login result.'))
                    if not result.get('ok'):
                        bot.manual_recovery('Automatic login did not complete. Log in manually in the current browser and resume at the main menu.')
                finally:
                    credentials.clear()
            ready = bot.enter_creation()
            if not ready:
                try:
                    ready = bot.enter_recipient_form()
                except UserError as error:
                    print(str(error))
                if not ready:
                    print('\nKeep/select the sender, then click 「お届け先の入力」 to open a blank recipient form.')
                    input('When the recipient form is visible, press Enter here to fill and register: ')
            if urlparse(bot.page.url).path != RECIPIENT:
                raise UserError('Recipient input page M060400.do not reached; nothing filled.')
            result = bot.run(ledger, key, args.stop_before_register)
            if result in ['print_clicked', 'print_preview', 'manual_print']:
                print('Complete printing manually. No further page actions, PDF capture or label creation will run.')
                input('Browser remains open. After printing, press Enter to close it: ')
            else:
                input('Stopped at review. Press Enter after checking to close the browser: ')
        except Exception as error:
            print('Automation paused/failed. Registration will not retry automatically; browser left open for inspection.')
            print('Failure type: ' + type(error).__name__ + '; stage: ' + getattr(bot, 'current_step', 'login or creation flow') + '; current page: ' + urlparse(bot.page.url).path.split(';')[0])
            try:
                input('After checking the website, press Enter to close (Ctrl+C to exit): ')
            except (KeyboardInterrupt, EOFError):
                pass
            raise
        finally:
            for resource in (context, browser):
                try:
                    resource.close()
                except Exception:
                    # Browser may already have been closed manually or disconnected.
                    pass
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (UserError, ValueError, OSError) as error:
        print('Not completed: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nStopped. Check whether the website created a label before retrying.')
        sys.exit(130)
    except Exception:
        # Do not dump Playwright call logs, form values or credentials.
        print('Browser action did not complete. Inspect the page; if registration was attempted, check website records before rerunning.', file=sys.stderr)
        sys.exit(1)
