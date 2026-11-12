function contentLabel(e){return e.getAttribute('aria-label')||e.getAttribute('alt')||e.getAttribute('title')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';}
function contentNorm(s){return(s||'').normalize('NFKC').replace(/\s/g,'');}
function contentVisible(e){return !!e.getClientRects().length&&!e.disabled;}
function contentPage(){const text=contentNorm(document.body?.innerText||'');const correct=location.pathname==='/mypage/M060800.do'||text.includes('内容品を登録する')||(text.includes('発送種別の選択')&&text.includes('EMS'));if(location.origin!=='https://www.int-mypage.post.japanpost.jp'||!correct)throw Error('当前不是内容品登记页。');}
function contentOne(values,label){let list=[...new Set(values)];list=list.filter(e=>!list.some(other=>other!==e&&typeof other.contains==='function'&&other.contains(e)));if(list.length!==1)throw Error('无法唯一识别'+label+'（'+list.length+'个），请检查官网。');return list[0];}
function contentButtons(root=document){return [...root.querySelectorAll('button,a,input[type="button"],input[type="submit"],input[type="image"],img,[onclick],[role="button"]')].filter(contentVisible);}
function markEMSContent(){
  try{
    contentPage();
    let targets=contentButtons().filter(e=>/^EMS\(物品\)(または税関検査対象)?$/.test(contentNorm(contentLabel(e))));
    targets=targets.map(e=>e.closest('a,button,[onclick],[role="button"],label')||e);
    targets=[...new Set(targets)].filter(e=>!targets.some(other=>other!==e&&other.contains(e)));
    const target=contentOne(targets,'EMS（物品）');
    const images=[...target.querySelectorAll('img,input[type="image"]')].filter(contentVisible);
    const matching=images.filter(e=>/^EMS\(物品\)(または税関検査対象)?$/.test(contentNorm(contentLabel(e))));
    const clickTarget=matching.length===1?matching[0]:images.length===1?images[0]:target;
    document.querySelectorAll('[data-jp-content-service]').forEach(e=>e.removeAttribute('data-jp-content-service'));
    clickTarget.setAttribute('data-jp-content-service','true');return {ok:true,targetTag:clickTarget.tagName};
  }catch(e){return {ok:false,message:e.message};}
}
function contentTextInputs(root){return [...root.querySelectorAll('input:not([type]),input[type="text"],input[type="number"]')].filter(contentVisible);}
function markContentInputs(){
  try{
    contentPage();
    const all=contentTextInputs(document);
    const aliases={name:['内容品名'],unitPrice:['単価'],quantity:['個数'],weightGrams:['重量g/個'],hsCode:['HSコード']};
    const fields={};
    for(const [key,names] of Object.entries(aliases)){
      const found=all.filter(e=>names.some(n=>contentNorm(e.placeholder)===n));
      if(found.length===1)fields[key]=found[0];
      else if(found.length>1)throw Error('输入框重复：'+key);
    }
    if(Object.keys(fields).length<5){
      let row=fields.name?.closest('tr');
      if(!row)row=contentOne([...document.querySelectorAll('tr')].filter(r=>{
        const c=[...r.children].filter(e=>['TD','TH'].includes(e.tagName));
        return c.length>=5&&contentTextInputs(c[0]).length===1&&contentTextInputs(c[1]).length===1&&contentTextInputs(c[2]).length>=1&&contentTextInputs(c[3]).length===1;
      }),'内容品输入行');
      const c=[...row.children].filter(e=>['TD','TH'].includes(e.tagName));
      if(c.length<5)throw Error('内容品输入行列数不足。');
      fields.name??=contentOne(contentTextInputs(c[0]),'内容品名');
      fields.unitPrice??=contentOne(contentTextInputs(c[1]),'単価');
      fields.quantity??=contentOne(contentTextInputs(c[3]),'個数');
      const weightAndHS=contentTextInputs(c[2]);
      fields.weightGrams??=weightAndHS[0];
      if(!fields.hsCode){
        if(weightAndHS.length===2)fields.hsCode=weightAndHS[1];
        else {
          const next=row.nextElementSibling;
          const nextCells=next?[...next.children].filter(e=>['TD','TH'].includes(e.tagName)):[];
          if(nextCells.length===2)fields.hsCode=contentOne(contentTextInputs(nextCells[1]),'下一行 HS代码');
        }
      }
    }
    for(const key of Object.keys(aliases))if(!fields[key])throw Error('未识别输入框：'+key+'；输入区可能尚未展开。');
    const selects=[...document.querySelectorAll('select')].filter(contentVisible);
    fields.currency=contentOne(selects.filter(el=>[...el.options].some(o=>contentNorm(o.textContent)==='JPY/円')),'币种');
    const countryNorm=s=>contentNorm(s).replace(/[()]/g,'').toUpperCase();
    fields.origin=contentOne(selects.filter(el=>el!==fields.currency&&[...el.options].some(o=>o.value==='JP'||['JAPAN','日本','JAPAN日本','日本JAPAN'].includes(countryNorm(o.textContent)))),'原产国下拉框');
    fields.confirm=contentOne(contentButtons().filter(el=>contentNorm(contentLabel(el))==='確定'),'確定');
    if(new Set(Object.values(fields)).size!==Object.keys(fields).length)throw Error('内容品输入框对应关系重复。');
    for(const [key,el] of Object.entries(fields)){
      document.querySelectorAll('[data-jp-content-'+key+']').forEach(e=>e.removeAttribute('data-jp-content-'+key));
      el.setAttribute('data-jp-content-'+key,'true');
    }
    return {ok:true};
  }catch(e){return {ok:false,message:e.message};}
}
function registeredContents(){
  contentPage();
  return [...document.querySelectorAll('tr')].filter(row=>{
    const cells=[...row.children].filter(e=>['TD','TH'].includes(e.tagName));
    return cells.length>=5&&contentButtons(cells[cells.length-1]).some(e=>contentNorm(contentLabel(e))==='削除');
  }).map(row=>{
    const cells=[...row.children].filter(e=>['TD','TH'].includes(e.tagName));
    const quantity=contentTextInputs(cells[3]);
    return {name:cells[0].textContent.trim(),priceOrigin:cells[1].textContent.trim(),weightHS:cells[2].textContent.trim(),quantity:quantity.length===1?quantity[0].value:cells[3].textContent.trim()};
  });
}
if(typeof module!=='undefined')module.exports={markEMSContent,markContentInputs,registeredContents};
