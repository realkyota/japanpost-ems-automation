function parseShipment(text) {
  const data=JSON.parse(text.replace(/^\s*```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, ''));
  if(!data || Array.isArray(data) || typeof data!=='object')throw Error('Shipment data must be a JSON object.');
  const allowed=['item','category','paid','invoice','noDangerousGoods','shipDate','totalWeightGrams','insuredValueYen'];
  for(const key of Object.keys(data))if(!allowed.includes(key))throw Error('Unknown shipment field: '+key);
  for(const k of ['paid','noDangerousGoods'])if(k in data && typeof data[k]!=='boolean')throw Error(k+' must be true or false.');
  for(const k of ['category','invoice','shipDate','totalWeightGrams','insuredValueYen'])if(k in data && typeof data[k]!=='string')throw Error(k+' must be a string.');
  if(data.invoice && data.invoice!=='prescribed')throw Error('Only invoice: prescribed is supported.');
  if(data.shipDate && !/^\d{4}\/\d{2}\/\d{2}$/.test(data.shipDate))throw Error('shipDate must use YYYY/MM/DD format.');
  for(const k of ['totalWeightGrams','insuredValueYen'])if(data[k]!==undefined && !/^\d+$/.test(data[k]))throw Error(k+' must be a nonnegative integer string.');
  if(data.item){
    if(Array.isArray(data.item)||typeof data.item!=='object')throw Error('item must be an object.');
    for(const k of Object.keys(data.item))if(!['name','unitPrice','quantity','weightGrams','origin','hsCode'].includes(k))throw Error('Unknown item field: '+k);
    for(const k of ['name','unitPrice','quantity'])if(typeof data.item[k]!=='string'||!data.item[k].trim())throw Error('Missing item.'+k+' string.');
    if(!/^[\x20-\x7E]+$/.test(data.item.name))throw Error('Item name must use printable ASCII characters.');
    if(!/^\d+(\.\d{1,2})?$/.test(data.item.unitPrice))throw Error('Invalid unitPrice format.');
    if(!/^[1-9]\d*$/.test(data.item.quantity))throw Error('quantity must be a positive integer string.');
    for(const k of ['weightGrams','origin','hsCode'])if(k in data.item && typeof data.item[k]!=='string')throw Error('item.'+k+' must be a string.');
    if(data.item.weightGrams && !/^[1-9]\d*$/.test(data.item.weightGrams))throw Error('Item weight must be a positive integer string.');
    if(data.item.origin && !/^[A-Z]{2}$/.test(data.item.origin))throw Error('origin must use a two-letter uppercase country code.');
    if(data.item.hsCode && !/^\d{6,10}$/.test(data.item.hsCode))throw Error('HS code must contain 6 to 10 digits.');
  }
  if(data.category==='贈物' && data.paid===true)throw Error('Gift category conflicts with paid:true; provide the actual purpose.');
  return data;
}

function operateShipment(data, action) {
  try {
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp')throw Error('Use this on the official Japan Post website.');
    const norm=s=>(s||'').normalize('NFKC').replace(/\s/g,'');
    const bodyText=norm(document.body?.textContent||'');
    const isContents=location.pathname==='/mypage/M060800.do'||bodyText.includes('内容品を登録する')||(bodyText.includes('発送種別の選択')&&bodyText.includes('EMS'));
    const visible=e=>e.getClientRects().length&&!e.disabled;
    const one=(items,label)=>{const a=[...new Set(items)];if(a.length!==1)throw Error('Cannot uniquely identify 「'+label+'; no action performed.');return a[0];};
    const description=e=>e.getAttribute('aria-label')||e.getAttribute('alt')||e.getAttribute('title')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';
    const clickables=()=>[...document.querySelectorAll('button,input[type="button"],input[type="submit"],input[type="image"],a,[role="button"],img[onclick]')].filter(visible);
    const byText=text=>one(clickables().filter(e=>norm(description(e))===norm(text)),text);
    const rowFor=text=>one([...document.querySelectorAll('tr')].filter(r=>{const c=r.querySelector(':scope > td,:scope > th');return c&&norm(c.textContent).startsWith(norm(text));}),text);
    const controls=row=>[...row.querySelectorAll('input:not([type]),input[type="text"],input[type="number"],select,textarea')].filter(visible);
    const changes=[];
    const add=(el,value)=>{
      if(typeof value!=='string')throw Error('Input value must be a string.');
      if(el.maxLength>=0 && value.length>el.maxLength)throw Error('Input exceeds the website length limit; not filled.');
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
        for(const x of changes){if(!x.el.isConnected)throw Error('The page changed');const proto=x.el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(x.el,x.value);x.el.dispatchEvent(new Event('input',{bubbles:true}));x.el.dispatchEvent(new Event('change',{bubbles:true}));}
        if(changes.some(x=>!x.el.isConnected||x.el.value!==x.value))throw Error('The page did not retain input values');
      }catch(e){for(const x of changes)if(x.el.isConnected)x.el.value=x.old;throw Error(e.message+'; attempted to restore input. Check the website.');}
    };
    if(action==='register'){
      if(!bodyText.includes('登録内容をご確認ください'))throw Error('Not on the registration review page.');
      byText('送り状を登録する').click();
      return {ok:true,message:'Clicked 「送り状を登録する」. Check the website response; registration success is not confirmed.'};
    }
    if(action==='ems'){
      if(!isContents)throw Error('Open the contents registration page.');
      const ems=one(clickables().filter(el=>/^EMS\(物品\)(または税関検査対象)?$/.test(norm(description(el)))),'EMS（物品）');
      ems.click();return {ok:true,message:'Clicked EMS（物品）. Check the selection before filling the item.'};
    }
    if(action==='item'){
      if(!isContents)throw Error('Open the contents registration page.');
      if(!data.item)throw Error('Missing item data.');
      if(clickables().some(el=>norm(description(el))==='削除'))throw Error('An item is already registered; no addition or edit performed. Keep it or edit/delete it on the website first.');
      const input=(placeholder)=>one([...document.querySelectorAll('input')].filter(el=>visible(el)&&norm(el.placeholder)===norm(placeholder)),placeholder);
      const name=input('内容品名');const row=name.closest('tr');if(!row)throw Error('Cannot find the item input row.');
      const item=data.item;
      add(name,item.name);add(input('単価'),item.unitPrice);add(input('個数'),item.quantity);
      add(input('重量 g/個'),item.weightGrams||'');add(input('HSコード'),item.hsCode||'');
      const selects=[...row.querySelectorAll('select')].filter(visible);
      const currency=one(selects.filter(el=>[...el.options].some(o=>norm(o.textContent)==='JPY/円')),'JPY/円');select(currency,['JPY/円','JPY']);
      const origin=one(selects.filter(el=>el!==currency),'原産国名');
      if(item.origin){const names=[item.origin];for(const locale of ['en','ja'])names.push(new Intl.DisplayNames([locale],{type:'region'}).of(item.origin));select(origin,names);}else add(origin,'');
      apply();return {ok:true,message:'Filled item draft (JPY). Review and click 「確定」, then set category and dangerous-goods declaration.'};
    }
    if(action==='declaration'){
      if(!isContents)throw Error('Open the contents registration page.');
      let checkbox;
      if(data.noDangerousGoods===true){
        const boxes=[...document.querySelectorAll('input[type="checkbox"]')].filter(visible).filter(el=>{
          let p=el;for(let i=0;i<5&&p;i++,p=p.parentElement){const t=norm(p.textContent);if(t.length<1200&&t.includes('危険物に該当しない')&&t.includes('開披'))return true;}
          return [...el.labels||[]].some(l=>norm(l.textContent).includes('危険物に該当しない'));
        });checkbox=one(boxes,'dangerous-goods declaration and inspection consent');
      }
      if(data.category)select(one(controls(rowFor('内容品種別')).filter(e=>e.tagName==='SELECT'),'内容品種別'),[data.category]);
      if(!checkbox&&!changes.length)throw Error('category or noDangerousGoods:true is required.');
      apply();if(checkbox&&!checkbox.checked)checkbox.click();
      if(checkbox&&!checkbox.checked)throw Error('Website did not retain the checkbox state; check manually.');
      return {ok:true,message:'Set item category from input'+(checkbox?' and selected dangerous-goods declaration and inspection consent':'')+'. Review and click 「次へ」.'};
    }
    if(action==='dispatch'){
      if(!bodyText.includes('発送関連情報登録'))throw Error('Open the dispatch information page.');
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
      if(!changes.length&&!radios.length)throw Error('Missing dispatch data.');
      apply();for(const el of radios)if(!el.checked)el.click();
      if(radios.some(el=>!el.checked))throw Error('Website did not retain selections; check the page.');
      return {ok:true,message:'Filled supplied dispatch information; unspecified fields kept their current values. Review date and total weight, then click 「次へ」.'};
    }
    throw Error('Unsupported operation.');
  }catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={parseShipment,operateShipment};
