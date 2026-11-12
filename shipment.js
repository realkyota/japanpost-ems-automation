function parseShipment(text) {
  const data=JSON.parse(text.replace(/^\s*```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, ''));
  if(!data || Array.isArray(data) || typeof data!=='object')throw Error('包裹数据必须是 JSON 对象。');
  const allowed=['item','category','paid','invoice','noDangerousGoods','shipDate','totalWeightGrams','insuredValueYen'];
  for(const key of Object.keys(data))if(!allowed.includes(key))throw Error('未知包裹字段：'+key);
  for(const k of ['paid','noDangerousGoods'])if(k in data && typeof data[k]!=='boolean')throw Error(k+' 必须为 true 或 false。');
  for(const k of ['category','invoice','shipDate','totalWeightGrams','insuredValueYen'])if(k in data && typeof data[k]!=='string')throw Error(k+' 必须是字符串。');
  if(data.invoice && data.invoice!=='prescribed')throw Error('本版仅适配 invoice: prescribed（规定份数）。');
  if(data.shipDate && !/^\d{4}\/\d{2}\/\d{2}$/.test(data.shipDate))throw Error('shipDate 格式为 YYYY/MM/DD。');
  for(const k of ['totalWeightGrams','insuredValueYen'])if(data[k]!==undefined && !/^\d+$/.test(data[k]))throw Error(k+' 应为非负整数字符串。');
  if(data.item){
    if(Array.isArray(data.item)||typeof data.item!=='object')throw Error('item 必须是对象。');
    for(const k of Object.keys(data.item))if(!['name','unitPrice','quantity','weightGrams','origin','hsCode'].includes(k))throw Error('未知内容品字段：'+k);
    for(const k of ['name','unitPrice','quantity'])if(typeof data.item[k]!=='string'||!data.item[k].trim())throw Error('缺少 item.'+k+' 字符串。');
    if(!/^[\x20-\x7E]+$/.test(data.item.name))throw Error('内容品名称请使用英文半角字符。');
    if(!/^\d+(\.\d{1,2})?$/.test(data.item.unitPrice))throw Error('unitPrice 格式错误。');
    if(!/^[1-9]\d*$/.test(data.item.quantity))throw Error('quantity 必须为正整数字符串。');
    for(const k of ['weightGrams','origin','hsCode'])if(k in data.item && typeof data.item[k]!=='string')throw Error('item.'+k+' 必须是字符串。');
    if(data.item.weightGrams && !/^[1-9]\d*$/.test(data.item.weightGrams))throw Error('内容品重量必须为正整数字符串。');
    if(data.item.origin && !/^[A-Z]{2}$/.test(data.item.origin))throw Error('origin 使用两位大写国家代码。');
    if(data.item.hsCode && !/^\d{6,10}$/.test(data.item.hsCode))throw Error('HS code 应为6至10位数字。');
  }
  if(data.category==='贈物' && data.paid===true)throw Error('贈物与 paid:true 不一致，请按实际用途填写。');
  return data;
}

function operateShipment(data, action) {
  try {
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp')throw Error('请在日本邮政官网使用。');
    const norm=s=>(s||'').normalize('NFKC').replace(/\s/g,'');
    const bodyText=norm(document.body?.textContent||'');
    const isContents=location.pathname==='/mypage/M060800.do'||bodyText.includes('内容品を登録する')||(bodyText.includes('発送種別の選択')&&bodyText.includes('EMS'));
    const visible=e=>e.getClientRects().length&&!e.disabled;
    const one=(items,label)=>{const a=[...new Set(items)];if(a.length!==1)throw Error('无法唯一识别「'+label+'」，未继续操作。');return a[0];};
    const description=e=>e.getAttribute('aria-label')||e.getAttribute('alt')||e.getAttribute('title')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';
    const clickables=()=>[...document.querySelectorAll('button,input[type="button"],input[type="submit"],input[type="image"],a,[role="button"],img[onclick]')].filter(visible);
    const byText=text=>one(clickables().filter(e=>norm(description(e))===norm(text)),text);
    const rowFor=text=>one([...document.querySelectorAll('tr')].filter(r=>{const c=r.querySelector(':scope > td,:scope > th');return c&&norm(c.textContent).startsWith(norm(text));}),text);
    const controls=row=>[...row.querySelectorAll('input:not([type]),input[type="text"],input[type="number"],select,textarea')].filter(visible);
    const changes=[];
    const add=(el,value)=>{
      if(typeof value!=='string')throw Error('输入值必须是字符串。');
      if(el.maxLength>=0 && value.length>el.maxLength)throw Error('输入超过官网长度限制，未填写。');
      changes.push({el,value,old:el.value});
    };
    const select=(el,names)=>{
      const o=one([...el.options].filter(o=>!o.disabled&&o.value&&names.some(n=>norm(o.value)===norm(n)||norm(o.textContent)===norm(n))),names.join('/'));
      add(el,o.value);
    };
    const dateKey=value=>{
      const text=(value||'').normalize('NFKC').trim();
      const match=text.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})/)||text.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日/)||text.match(/^(\d{4})(\d{2})(\d{2})$/);
      return match?match[1]+'/'+match[2].padStart(2,'0')+'/'+match[3].padStart(2,'0'):'';
    };
    const radio=(row,text)=>{
      const candidates=[...row.querySelectorAll('input[type="radio"]')].filter(visible).filter(el=>{
        const associated=[...el.labels||[]].map(l=>norm(l.textContent));
        let adjacent='';for(let n=el.nextSibling;n;n=n.nextSibling){if(n.nodeType===1 && (n.matches('input,select,br')||n.querySelector('input[type="radio"]')))break;adjacent+=n.textContent||'';}
        return [...associated,norm(adjacent)].some(t=>t===norm(text)||t.startsWith(norm(text)+'('));
      });
      return one(candidates,text);
    };
    const apply=()=>{
      try{
        for(const x of changes){if(!x.el.isConnected)throw Error('页面已变化');const proto=x.el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(x.el,x.value);x.el.dispatchEvent(new Event('input',{bubbles:true}));x.el.dispatchEvent(new Event('change',{bubbles:true}));}
        if(changes.some(x=>!x.el.isConnected||x.el.value!==x.value))throw Error('页面未保留输入值');
      }catch(e){for(const x of changes)if(x.el.isConnected)x.el.value=x.old;throw Error(e.message+'，已尝试恢复输入，请检查官网。');}
    };
    if(action==='register'){
      if(!bodyText.includes('登録内容をご確認ください'))throw Error('当前不是登记确认页。');
      byText('送り状を登録する').click();
      return {ok:true,message:'已点击官网「送り状を登録する」。请查看官网返回结果；尚未确认登记成功。'};
    }
    if(action==='ems'){
      if(!isContents)throw Error('请进入内容品登记页面。');
      const ems=one(clickables().filter(el=>/^EMS\(物品\)(または税関検査対象)?$/.test(norm(description(el)))),'EMS（物品）');
      ems.click();return {ok:true,message:'已点击 EMS（物品）。请检查官网选中状态，再填写内容品。'};
    }
    if(action==='item'){
      if(!isContents)throw Error('请进入内容品登记页面。');
      if(!data.item)throw Error('缺少 item 内容品数据。');
      if(clickables().some(el=>norm(description(el))==='削除'))throw Error('已有登记内容品，未新增或修改，避免重复。要保留现有内容品时可跳过这一步；更换时请先在官网编辑或删除。');
      const input=(placeholder)=>one([...document.querySelectorAll('input')].filter(el=>visible(el)&&norm(el.placeholder)===norm(placeholder)),placeholder);
      const name=input('内容品名');const row=name.closest('tr');if(!row)throw Error('找不到内容品输入行。');
      const item=data.item;
      add(name,item.name);add(input('単価'),item.unitPrice);add(input('個数'),item.quantity);
      add(input('重量 g/個'),item.weightGrams||'');add(input('HSコード'),item.hsCode||'');
      const selects=[...row.querySelectorAll('select')].filter(visible);
      const currency=one(selects.filter(el=>[...el.options].some(o=>norm(o.textContent)==='JPY/円')),'JPY/円');select(currency,['JPY/円','JPY']);
      const origin=one(selects.filter(el=>el!==currency),'原産国名');
      if(item.origin){const names=[item.origin];for(const locale of ['en','ja'])names.push(new Intl.DisplayNames([locale],{type:'region'}).of(item.origin));select(origin,names);}else add(origin,'');
      apply();return {ok:true,message:'已填内容品草稿（JPY）。请检查后点击官网「確定」登记该条目，然后执行类别与无危险品勾选。'};
    }
    if(action==='declaration'){
      if(!isContents)throw Error('请进入内容品登记页面。');
      let checkbox;
      if(data.noDangerousGoods===true){
        const boxes=[...document.querySelectorAll('input[type="checkbox"]')].filter(visible).filter(el=>{
          let p=el;for(let i=0;i<5&&p;i++,p=p.parentElement){const t=norm(p.textContent);if(t.length<1200&&t.includes('危険物に該当しない')&&t.includes('開披'))return true;}
          return [...el.labels||[]].some(l=>norm(l.textContent).includes('危険物に該当しない'));
        });checkbox=one(boxes,'无危险品及开封检查同意');
      }
      if(data.category)select(one(controls(rowFor('内容品種別')).filter(e=>e.tagName==='SELECT'),'内容品種別'),[data.category]);
      if(!checkbox&&!changes.length)throw Error('需要 category 或 noDangerousGoods:true。');
      apply();if(checkbox&&!checkbox.checked)checkbox.click();
      if(checkbox&&!checkbox.checked)throw Error('官网未保留勾选状态，请手动检查。');
      return {ok:true,message:'已按数据设置内容品类别'+(checkbox?'，并勾选无危险品及开封检查同意':'')+'。请检查后点击官网「次へ」。'};
    }
    if(action==='dispatch'){
      if(!bodyText.includes('発送関連情報登録'))throw Error('请进入発送相关信息登记页。');
      if(data.shipDate){
        const el=one(controls(rowFor('発送予定日')),'発送予定日');
        const option=one([...el.options].filter(o=>!o.disabled&&o.value&&(dateKey(o.value)===data.shipDate||dateKey(o.textContent)===data.shipDate)),'発送予定日 '+data.shipDate);
        add(el,option.value);
      }
      if(data.totalWeightGrams!==undefined)add(one(controls(rowFor('総重量')),'総重量'),data.totalWeightGrams);
      if(data.insuredValueYen!==undefined)add(one(controls(rowFor('損害要償額')),'損害要償額'),data.insuredValueYen);
      const radios=[];
      if(data.invoice==='prescribed')radios.push(radio(rowFor('インボイス印刷指定'),'規定枚数印刷する'));
      if(typeof data.paid==='boolean')radios.push(radio(rowFor('有償/無償'),data.paid?'有償':'無償'));
      if(!changes.length&&!radios.length)throw Error('缺少発送相关数据。');
      apply();for(const el of radios)if(!el.checked)el.click();
      if(radios.some(el=>!el.checked))throw Error('官网未保留选项，请检查页面。');
      return {ok:true,message:'已填写提供的発送信息。未提供的字段保留官网当前值，请核对日期及包裹总重量后点击「次へ」。'};
    }
    throw Error('不支持的操作。');
  }catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={parseShipment,operateShipment};
