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
        raise UserError('资料必须为 JSON 对象。')
    if set(data) - {'recipient', 'shipment', '_example'}:
        raise UserError('顶层只支持 recipient、shipment 和 _example。')
    if data.get('_example', False) is not False:
        raise UserError('这是演示资料，不能出单。请填入真实资料并删除 _example 字段。')
    recipient, shipment = data.get('recipient'), data.get('shipment')
    if not isinstance(recipient, dict) or not isinstance(shipment, dict):
        raise UserError('缺少 recipient 或 shipment 对象。')
    keys = {'name', 'country', 'address1', 'address2', 'city', 'state', 'postalCode', 'phone', 'fax', 'email'}
    if set(recipient) - keys:
        raise UserError('收件人资料中有不支持的字段。')
    for key in keys:
        value = recipient.get(key, '')
        if not isinstance(value, str) or re.search(r'[\x00-\x1f]', value):
            raise UserError(f'recipient.{key} 必须是无换行的字符串。')
    for key in ['name', 'country', 'address2', 'city']:
        if not recipient.get(key, '').strip():
            raise UserError(f'缺少 recipient.{key}。')
    if not re.fullmatch('[A-Z]{2}', recipient['country']):
        raise UserError('country 必须为两位大写国家/地区代码。')
    if recipient.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', recipient['email']):
        raise UserError('收件人邮箱格式错误。')
    allowed = {'item', 'category', 'paid', 'invoice', 'noDangerousGoods', 'shipDate', 'totalWeightGrams', 'insuredValueYen'}
    if set(shipment) - allowed:
        raise UserError('包裹资料中有不支持的字段。')
    if shipment.get('noDangerousGoods') is not True:
        raise UserError('请确认内容物不含危险品；确认后设置 noDangerousGoods:true。')
    if type(shipment.get('paid')) is not bool:
        raise UserError('paid 必须明确填写 true（销售）或 false（无偿）。')
    if not isinstance(shipment.get('category'), str) or not shipment['category']:
        raise UserError('请填写官网显示的内容品类别 category。')
    if shipment['category'] == '贈物' and shipment['paid']:
        raise UserError('贈物与 paid:true 冲突。')
    if shipment.get('invoice') != 'prescribed':
        raise UserError('本版 invoice 必须填写 prescribed（规定份数）。')
    if 'shipDate' in shipment:
        try:
            if not re.fullmatch(r'\d{4}/\d{2}/\d{2}', shipment['shipDate']):
                raise ValueError()
            datetime.strptime(shipment['shipDate'], '%Y/%m/%d')
        except (ValueError, TypeError):
            raise UserError('shipDate 必须为有效日期 YYYY/MM/DD。') from None
    item = shipment.get('item')
    if not isinstance(item, dict) or set(item) - {'name', 'unitPrice', 'quantity', 'weightGrams', 'origin', 'hsCode'}:
        raise UserError('本版需填写一条 item 对象。')
    # User-confirmed fixed parcel settings; explicit JSON values may override these.
    item.setdefault('origin', 'JP')
    item.setdefault('hsCode', '9503002190')
    for key in ['name', 'unitPrice', 'quantity']:
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise UserError(f'缺少字符串 item.{key}。')
    if not re.fullmatch(r'[\x20-\x7e]+', item['name']):
        raise UserError('内容品名称须为英文半角字符。')
    if not re.fullmatch(r'\d+(\.\d{1,2})?', item['unitPrice']):
        raise UserError('unitPrice 必须为金额字符串，本版货币为 JPY。')
    if not re.fullmatch(r'[1-9]\d*', item['quantity']):
        raise UserError('quantity 必须为正整数字符串。')
    for obj, key in [(item, 'weightGrams'), (shipment, 'totalWeightGrams'), (shipment, 'insuredValueYen')]:
        if key in obj and (not isinstance(obj[key], str) or not re.fullmatch(r'\d+', obj[key])):
            raise UserError(f'{key} 必须为非负整数字符串。')
    if item.get('origin') is not None and (not isinstance(item['origin'], str) or not re.fullmatch('[A-Z]{2}', item['origin'])):
        raise UserError('item.origin 必须为两位大写原产国代码。')
    if item.get('hsCode') is not None and (not isinstance(item['hsCode'], str) or not re.fullmatch(r'\d{6,10}', item['hsCode'])):
        raise UserError('hsCode 必须为6至10位数字字符串。')
    if item.get('weightGrams') and shipment.get('totalWeightGrams'):
        if int(item['weightGrams']) * int(item['quantity']) > int(shipment['totalWeightGrams']):
            raise UserError('包裹总重量小于物品重量合计，请检查。')
    return data


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def with_next_day(data, started_at):
    if started_at.tzinfo is None:
        raise UserError('运行时间必须包含时区。')
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
        raise UserError('无法唯一匹配原产国下拉选项：' + code)
    return matches[0]


class Ledger:
    """Only hashes/status are saved. Never retry registration implicitly."""
    def __init__(self, directory):
        self.path = directory / 'run-state.json'
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}

    def check(self, key, allow_repeat=False):
        if key in self.records and not allow_repeat:
            when = self.records[key].get('time', '时间未知')
            raise UserError('防重复出单：同一份资料已有登记尝试（'+when+'）。这不是「送り状作成」按钮错误。请先到官网「発送予定データ」核查；明确需要另一张新单时才使用 --allow-repeat。请保留 run-state.json。')

    def attempted(self, key):
        self.records[key] = {'status': 'registration_attempted', 'time': datetime.now(JST).isoformat()}
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.records, indent=2))
        os.chmod(temp, 0o600)
        temp.replace(self.path)


def choose_file():
    if sys.platform != 'darwin':
        raise UserError('请通过命令行指定 JSON 文件。')
    result = subprocess.run(['osascript', '-e', 'POSIX path of (choose file with prompt "选择收件人和包裹 JSON 文件")'], capture_output=True, text=True)
    if result.returncode:
        raise UserError('未选择资料文件。')
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
        print('已保存官网 PDF：', path)

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
            raise UserError('当前页面不在日本邮政官网。')
        for name in ['recipient.js', 'shipment.js', 'login.js', 'navigation.js', 'content.js']:
            self.page.add_script_tag(content=(ROOT / name).read_text())

    def operate(self, action):
        if action == 'register':
            self.click(['送り状を登録する'])
            return
        self.load_helpers()
        result = self.page.evaluate('args => operateShipment(args.data, args.action)', {'data': self.data['shipment'], 'action': action})
        if not result.get('ok'):
            raise UserError(result.get('message', '官网操作失败。'))

    def click_control(self, locator):
        images = locator.locator('img,input[type="image"]')
        visible = [images.nth(i) for i in range(images.count()) if images.nth(i).is_visible()]
        if len(visible) > 1:
            raise UserError('按钮内有多个可见图片，停止以避免点击错误目标。')
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
        raise UserError('无法唯一识别按钮：' + '/'.join(labels))

    def wait_ready(self):
        try:
            self.page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception:
            pass
        self.page.wait_for_timeout(400)

    def manual_recovery(self, message):
        if getattr(self,'journal',None):
            self.journal.event('paused',message=message[:240])
        print('\n暂停：' + message)
        input('请在浏览器中修正/完成当前步骤，然后回到终端按回车继续（Ctrl+C 退出）：')

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
            return {'ok': False, 'message': '官网登录提交脚本尚未就绪；未尝试登录。请在官网检查页面加载情况。'}
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
            return {'ok': False, 'message': '登录控件的实际填写/点击未完成，请查看官网页面是否有遮挡、验证或提示；不会自动重试。'}
        print('→ 已执行登录图片点击，等待官网提交结果')
        try:
            wait_stage(self.page, ['menu', 'resume_prompt'], timeout=20000)
        except Exception:
            return {'ok': False, 'message': '已点击「ログイン」，但尚未检测到主菜单。请检查官网的账号/密码错误、验证码或其他提示。'}
        return {'ok': True, 'message': '已检测到登录后的主菜单。'}

    def enter_creation(self):
        if getattr(self,'journal',None):self.journal.event('opening_label_creation')
        self._new_draft_clicked = False
        self._keyboard_menu_attempted = False
        self._menu_activation_log = []
        print('→ 等待登录后的日语主菜单')
        destinations = ['sender', 'recipient_selection', 'recipient_form']
        try:
            self.wait_flow_stage(['menu', 'resume_prompt'] + destinations)
        except Exception:
            self.manual_recovery('请完成登录/验证，选择日语界面，并停在主菜单或寄件人选择页。')
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
                        raise UserError('当前未识别为主菜单或创建流程：' + str(stage))
                    if menu_clicks >= 2:
                        raise UserError('主菜单已点击两次，未自动继续重试。')
                    menu_clicks += 1
                    print('→ 点击主菜单「送り状作成」')
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
                print('主菜单操作未完成：' + type(error).__name__)
                try:
                    path=write_menu_diagnostic(self.page,self.output,error,getattr(getattr(self,'context',None),'pages',[]),self._menu_activation_log)
                    print('已保存按钮诊断文件：' + str(path))
                    reveal_report(path)
                except Exception as diagnostic_error:
                    print('诊断保存失败：'+type(diagnostic_error).__name__+'；预期位置：'+str(getattr(self,'output',ROOT/'output')/'diagnostic-main-menu.json'))
                self.manual_recovery('尚未进入创建流程。若有前回数据弹窗，点击「新しく作成する」；若返回主菜单，再点击「送り状作成」，进入寄件人选择页后继续。')
        self.wait_ready()
        stage = self.page.evaluate(READ_STAGE)
        if stage not in destinations:
            raise UserError('尚未进入寄件人/收件人选择页，未开始出单。')
        return stage == 'recipient_form'

    def choose_new_draft(self):
        if self.page.evaluate(READ_STAGE) != 'resume_prompt':
            return False
        if self._new_draft_clicked:
            raise UserError('已尝试新建草稿，未自动重复点击，请检查官网。')
        print('→ 检测到前回数据弹窗，点击「新しく作成する」')
        self._new_draft_clicked = True
        self.click(['新しく作成する'])
        # Discarding the previous draft may return to the menu, rather than start it.
        result = self.wait_flow_stage(['menu', 'sender', 'recipient_selection', 'recipient_form'])
        if result == 'menu':
            print('→ 新建草稿后返回主菜单，将再次点击「送り状作成」')
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
                            print('→ 检测到官网新窗口，切换到创建流程')
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
        print('→ 页面仍停在主菜单且未观察到 POST，仅尝试一次键盘 Enter 激活')
        target.press('Enter',timeout=15000)
        return True

    def enter_recipient_form(self):
        if urlparse(self.page.url).path == RECIPIENT:
            return True
        self.wait_ready()
        text = re.sub(r'\s', '', self.page.locator('body').inner_text())
        if 'ご依頼主を選択する' in text:
            print('→ 保留当前寄件人，点击页面底部「次へ」')
            self.load_helpers()
            result = self.page.evaluate('markSenderNext()')
            if not result.get('ok'):
                raise UserError(result.get('message', '未能识别寄件人选择页。'))
            self.click_control(self.page.locator('[data-jp-ems-sender-next="true"]'))
            self.wait_ready()
            text = re.sub(r'\s', '', self.page.locator('body').inner_text())
        if urlparse(self.page.url).path == RECIPIENT:
            return True
        if 'お届け先を選択する' in text:
            print('→ 点击「お届け先の入力」，使用本次 JSON 收件人')
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
            raise UserError('未在页面确认已登记内容品，请检查官网错误提示。')

    def wait_for_contents(self):
        try:
            wait_stage(self.page, ['contents'])
        except Exception:
            path = urlparse(self.page.url).path.split(';')[0]
            raise UserError('未识别到内容品页面。当前路径：' + path + '。若官网已显示 EMS 选择区，请确认后继续；无需因 URL 附带参数而重新登录。') from None

    def select_ems_goods(self):
        with ActionAudit(self.page) as audit:
            try:
                self._select_ems_goods()
            except UserError:
                print('EMS 选择可能只切换页面显示，POST 次数不用于判断是否选中。')
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
            print('→ 已识别展开的内容品输入区')
        except PagePollTimeout as error:
            reason = error.last.get('message', '字段检查暂未返回结果') if isinstance(error.last,dict) else '字段检查暂未返回结果'
            raise UserError('EMS 点击后输入区识别未完成：' + reason) from None
        except UserError:
            raise
        except Exception:
            raise UserError('EMS（物品）实际点击后，未识别到展开的内容品输入区。请在官网选中 EMS（物品）后继续。') from None

    def fill_and_confirm_item(self):
        try:
            self.load_helpers()
            existing = self.page.evaluate('registeredContents()')
            if existing:
                raise UserError('当前已有登记内容品，未重复新增。请在官网核对/编辑为本次物品，再继续。')
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
                    raise UserError('内容品字段超出官网长度限制：' + key)
                control.fill(value)
                expected[key] = value
            currency = field('currency').select_option(label='JPY/円')
            options = field('origin').locator('option').evaluate_all('(els)=>els.map(o=>({value:o.value,label:o.textContent,disabled:o.disabled}))')
            origin_value = country_option(options, item['origin'])
            field('origin').select_option(value=origin_value)
            field('quantity').press('Tab')
            if any(field(key).input_value() != value for key, value in expected.items()):
                raise UserError('官网没有保留全部内容品输入值，未点击確定。')
            if field('origin').input_value() != origin_value or field('currency').input_value() not in currency:
                raise UserError('币种或原产国下拉选项未保留，未点击確定。')
            print('→ 内容品已填入，点击「確定」登记条目')
            self.click_control(field('confirm'))
            self.wait_ready()
            self.load_helpers()
            rows = poll_evaluate(self.page, 'registeredContents()', lambda value: isinstance(value,list) and len(value)>0, timeout=15000)
            if len(rows) != 1 or rows[0]['name'] != item['name'] or rows[0]['quantity'] != item['quantity']:
                raise UserError('未确认唯一的已登记内容品/数量，请在官网核对。')
        except UserError:
            raise
        except Exception:
            raise UserError('内容品填写、下拉选择或「確定」登记未完成，请检查官网当前页面；不会自动重复添加。') from None

    def confirmation(self):
        wait_stage(self.page, ['confirmation'])
        text = self.page.locator('body').inner_text()
        expected = [self.data['recipient']['name'], self.data['shipment']['item']['name'], 'EMS']
        if not all(value in text for value in expected):
            raise UserError('确认页缺少预期收件人、内容品或 EMS，停止自动登记。')

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
                self.manual_recovery('登记操作后返回主菜单。请先从「発送予定データ」核查并进入该记录的印刷页；不要重新创建。')
            else:
                self.manual_recovery('请在官网进入截图所示的送り状印刷页（M061000.do），然后继续。')
            stage = self.locate_print_page()
        if stage == 'print_preview':
            print('已进入官网 PDF/打印预览，自动操作已停止。')
            return 'print_preview'
        if stage != 'print_notice':
            print('未识别到印刷页，自动操作已停止，浏览器留给你处理。')
            return 'manual_print'
        return self.click_official_print()

    def click_official_print(self):
        if getattr(self, '_print_clicked', False):
            raise UserError('已尝试点击官方印刷按钮，不会重复点击。')
        if self.page.evaluate(READ_STAGE) != 'print_notice':
            raise UserError('当前不是官方印刷页，未点击。')
        self.current_step = '点击官方印刷按钮并停止'
        self._print_clicked = True
        self.printing_enabled = False
        self.click(['注意事項に同意して送り状を印刷', '注意事項に同意して印刷', '注意事項に同意して印刷する'])
        print('已点击「注意事項に同意して送り状を印刷」。自动操作已停止，浏览器保持打开。')
        return 'print_clicked'

    def run(self, ledger, key, stop_before_register):
        self.step('填写收件人', self.fill_recipient)
        self.step('进入内容品页', lambda: self.click(['次へ']))
        self.step('等待内容品页面就绪', lambda: self.wait_for_contents())
        self.step('选择 EMS（物品）并等待输入区展开', self.select_ems_goods)
        self.step('填写并登记一条内容品', self.fill_and_confirm_item)
        self.step('设置类别并勾选无危险品确认', lambda: self.operate('declaration'))
        self.step('进入発送信息页', lambda: self.click(['次へ']))
        self.step('填写発送信息', lambda: self.operate('dispatch'))
        self.step('进入登记确认页', lambda: self.click(['次へ']))
        self.confirmation()
        if stop_before_register:
            print('已按参数停在确认页，没有登记。')
            return
        # Write before dispatch: no automatic re-submit if navigation or output fails.
        ledger.attempted(key)
        self.printing_enabled = False
        print('→ 登记官方送り状（不会自动重试）')
        self.operate('register')
        self.wait_ready()
        return self.finish_printing()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mac 本地日本邮政 EMS 自动填写程序')
    parser.add_argument('file', nargs='?', type=Path, help='收件人和包裹 JSON；省略时弹出 Mac 文件选择框')
    login_modes = parser.add_mutually_exclusive_group()
    login_modes.add_argument('--login', action='store_true', help='本次在终端输入账号及隐藏密码，不保存')
    login_modes.add_argument('--setup-login', action='store_true', help='首次设置，保存登录资料到 Mac 钥匙串后退出')
    login_modes.add_argument('--forget-login', action='store_true', help='删除本程序的钥匙串登录资料后退出')
    login_modes.add_argument('--manual-login', action='store_true', help='本次忽略已保存账号，自行在浏览器登录')
    parser.add_argument('--print', dest='print_pdf', action='store_true', help='兼容旧参数；本版仅点击官网印刷按钮后停止')
    parser.add_argument('--stop-before-register', action='store_true', help='填写后停在确认页，不登记')
    parser.add_argument('--allow-repeat', action='store_true', help='已在官网核查后，允许同一资料再次登记')
    parser.add_argument('--validate-only', action='store_true', help='只检查 JSON，不打开浏览器')
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args(argv)
    started_at = datetime.now(JST)
    print('EMS 程序版本：' + BUILD)
    try:
        if args.setup_login:
            setup_login()
            return 0
        if args.forget_login:
            forget_login()
            print('已删除本程序的钥匙串登录资料。')
            return 0
    except RuntimeError as error:
        raise UserError(str(error)) from None
    output = args.output.resolve()
    try:
        journal = DiagnosticJournal(output, BUILD)
    except OSError as error:
        raise UserError('无法创建诊断文件：'+str(output/'diagnostic-main-menu.json')+'（'+type(error).__name__+'）') from None
    print('诊断文件完整路径：' + str(journal.path))
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
    print('発送予定日：' + data['shipment']['shipDate'] + '（程序启动当天日本日期的次日）')
    if args.validate_only:
        print('资料格式通过。尚未校验目的国规定、HS分类或官网字段。')
        return 0
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(output)
    if not args.stop_before_register:
        journal.event('checking_duplicate_record')
        ledger.check(key, args.allow_repeat)
    credentials = None
    if args.login:
        credentials = {'username': input('日本邮政登录邮箱 / ID：').strip(), 'password': getpass.getpass('密码（不显示、不保存）：')}
    elif not args.manual_login and sys.platform == 'darwin':
        try:
            credentials = load_saved()
            if credentials is None:
                print('未找到已保存登录资料。本次需手动登录；如需自动登录，请先运行 setup_login.command。')
        except RuntimeError as error:
            print(str(error))
            print('本次改为在浏览器中自行登录。')
    if args.print_pdf:
        print('本版只点击官网印刷按钮，不再发送系统打印任务。')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise UserError('缺少依赖，请先执行 bash run.command，或安装 requirements.txt。') from None
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
                    print('→ 自动填写并尝试登录日本邮政')
                    result = bot.login(credentials)
                    print(result.get('message', '请检查登录结果。'))
                    if not result.get('ok'):
                        bot.manual_recovery('自动登录未完成。你可以先在当前官网手动登录，停在主菜单后继续。')
                finally:
                    credentials.clear()
            ready = bot.enter_creation()
            if not ready:
                try:
                    ready = bot.enter_recipient_form()
                except UserError as error:
                    print(str(error))
                if not ready:
                    print('\n请在浏览器保留/选择寄件人，再点击「お届け先の入力」，打开收件人空白表单。')
                    input('看到收件人输入表单后，回到终端按回车，程序将连续填写并登记：')
            if urlparse(bot.page.url).path != RECIPIENT:
                raise UserError('尚未进入 M060400.do 收件人输入页；未开始填写。')
            result = bot.run(ledger, key, args.stop_before_register)
            if result in ['print_clicked', 'print_preview', 'manual_print']:
                print('后续打印由你处理；程序不会继续点页面、抓取 PDF 或再次出单。')
                input('浏览器保持打开。完成打印后，按回车关闭程序浏览器：')
            else:
                input('已停在确认页。检查完成后，按回车关闭程序浏览器：')
        except Exception as error:
            print('程序暂停/失败。不会自动重试登记；浏览器暂时保留供你检查。')
            print('失败类型：' + type(error).__name__ + '；阶段：' + getattr(bot, 'current_step', '登录或创建流程') + '；当前页面：' + urlparse(bot.page.url).path.split(';')[0])
            try:
                input('检查完官网后按回车关闭（Ctrl+C 退出）：')
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
        print('未完成：' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n已停止。请核查官网是否已生成送り状，勿直接重复出单。')
        sys.exit(130)
    except Exception:
        # Do not dump Playwright call logs, form values or credentials.
        print('浏览器操作未完成。请检查当前页面；若已尝试登记，请先核查官网历史再重跑。', file=sys.stderr)
        sys.exit(1)
