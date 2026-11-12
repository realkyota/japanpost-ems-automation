/* No network requests, no persistent storage. Also exported for local tests. */
function parseRecipient(text) {
  const data = JSON.parse(text.replace(/^\s*```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, ''));
  const keys = ['name','country','address1','address2','city','state','postalCode','phone','fax','email'];
  if (!data || Array.isArray(data) || typeof data !== 'object') throw Error('请输入一个收件人 JSON 对象。');
  for (const key of Object.keys(data)) if (!keys.includes(key)) throw Error('未知字段：' + key);
  const result = {};
  for (const key of keys) {
    if (data[key] !== undefined && typeof data[key] !== 'string') throw Error(key + ' 必须使用字符串，邮编和电话也要加双引号。');
    result[key] = (data[key] || '').trim();
    if (/[\r\n\u0000-\u001f]/.test(result[key])) throw Error(key + ' 不能包含换行或控制字符。');
  }
  for (const key of ['name','country','address2','city']) if (!result[key]) throw Error('缺少必填字段：' + key);
  result.country = result.country.toUpperCase();
  if (!/^[A-Z]{2}$/.test(result.country)) throw Error('country 请使用两位国家/地区代码，例如 US、DK、GB、TW。');
  if (result.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(result.email)) throw Error('邮箱格式不正确。');
  return result;
}

// Self-contained: passed to chrome.scripting.executeScript.
function fillJapanPost(recipient, testing = false) {
  try {
    if (!testing && (location.origin !== 'https://www.int-mypage.post.japanpost.jp' || location.pathname !== '/mypage/M060400.do')) {
      throw Error('请切换到日本邮政「お届け先情報の入力」页面（M060400.do）。');
    }
    const definitions = [
      ['name', /^お名前/], ['country', /^国名[・･]?地域/],
      ['address1', /^住所[1１]/], ['address2', /^住所[2２]/], ['city', /^住所[3３]/],
      ['state', /^州名/], ['postalCode', /^郵便番号/], ['phone', /^ご連絡先電話番号/],
      ['fax', /^ご連絡先FAX番号/i], ['email', /^メールアドレス/]
    ];
    const visible = e => !!e.getClientRects().length && !e.disabled && !e.readOnly;
    const norm = s => s.normalize('NFKC').replace(/[\s\u3000]/g, '').toUpperCase();
    const mapped = [];
    for (const [key, pattern] of definitions) {
      const candidates = [];
      for (const row of document.querySelectorAll('tr')) {
        const label = row.querySelector(':scope > th, :scope > td');
        if (!label || !pattern.test(label.textContent.replace(/\s/g, ''))) continue;
        const controls = [...row.querySelectorAll('input:not([type]),input[type="text"],input[type="email"],input[type="tel"],select,textarea')].filter(visible);
        if (controls.length === 1) candidates.push(controls[0]);
      }
      if (candidates.length !== 1) throw Error('无法唯一识别字段 ' + key + '。页面结构可能已变化，尚未填写任何内容。');
      mapped.push({key, el:candidates[0], value:recipient[key], old:candidates[0].value});
    }
    if (new Set(mapped.map(x=>x.el)).size !== mapped.length) throw Error('字段识别发生重复，已停止。');
    const forms = new Set(mapped.map(x=>x.el.form));
    if (forms.size !== 1) throw Error('字段不在同一表单，已停止。');
    const country = mapped.find(x=>x.key === 'country');
    if (country.el.tagName !== 'SELECT') throw Error('国名字段不是下拉菜单，已停止。');
    const aliases = {US:['UNITED STATES','UNITED STATES OF AMERICA','アメリカ合衆国','米国'],GB:['UNITED KINGDOM','GREAT BRITAIN','英国','イギリス'],DK:['DENMARK','デンマーク'],CN:['CHINA','中国'],TW:['TAIWAN','台湾'],HK:['HONG KONG','香港'],MO:['MACAO','MACAU','マカオ']};
    const names = [recipient.country, ...(aliases[recipient.country] || [])];
    for (const locale of ['en','ja']) {
      try { names.push(new Intl.DisplayNames([locale],{type:'region'}).of(recipient.country)); } catch {}
    }
    const matches = [...country.el.options].filter(o => !o.disabled && o.value && (
      norm(o.value) === recipient.country || names.some(n=>norm(o.textContent) === norm(n))
    ));
    if (matches.length !== 1) throw Error('无法唯一识别国名 ' + recipient.country + '，尚未填写。请把该国家在下拉菜单中的显示名称发给我。');
    country.value = matches[0].value;
    for (const x of mapped) {
      if (x.el.tagName === 'SELECT' && x !== country) throw Error('出现未适配的下拉字段：' + x.key);
      if (x.el.maxLength >= 0 && x.value.length > x.el.maxLength) throw Error(x.key + ' 超过官网长度限制 ' + x.el.maxLength + '，未填写。请重新拆分地址。');
    }
    // Set country first, then address fields. Never truncate or submit.
    const order = [country, ...mapped.filter(x=>x!==country)];
    try {
      for (const x of order) {
        if (!x.el.isConnected) throw Error('页面刷新了表单，请重试。');
        const proto = x.el.tagName === 'SELECT' ? HTMLSelectElement.prototype : x.el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto,'value').set.call(x.el,x.value);
        x.el.dispatchEvent(new Event('input',{bubbles:true}));
        x.el.dispatchEvent(new Event('change',{bubbles:true}));
      }
      if (mapped.some(x=>!x.el.isConnected || x.el.value !== x.value)) throw Error('官网未保留所有输入值。');
    } catch (error) {
      for (const x of mapped) if (x.el.isConnected) { x.el.value=x.old; x.el.dispatchEvent(new Event('change',{bubbles:true})); }
      throw Error(error.message + ' 已尝试恢复原值，请检查页面。');
    }
    mapped[0].el.focus();
    return {ok:true,message:'已填入 10 个收件人字段（空白可选项已清空）。请检查国名、地址和邮编，再点击官网「次へ」。'};
  } catch(error) { return {ok:false,message:error.message}; }
}
if (typeof module !== 'undefined') module.exports={parseRecipient,fillJapanPost};
