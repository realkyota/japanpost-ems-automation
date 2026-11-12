function markSenderNext() {
  try {
    const norm=s=>(s||'').normalize('NFKC').replace(/\s/g,'');
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp'||!norm(document.body?.innerText||'').includes('ご依頼主を選択する'))throw Error('当前不是寄件人选择页。');
    const visible=e=>e.getClientRects().length&&!e.disabled;
    const selected=[...document.querySelectorAll('input[type="radio"]')].filter(e=>visible(e)&&e.checked);
    if(selected.length!==1)throw Error('未找到唯一的当前寄件人，请在官网选择；程序不更换寄件人。');
    const label=e=>e.getAttribute('aria-label')||e.getAttribute('alt')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';
    let candidates=[...document.querySelectorAll('button,a,input[type="submit"],input[type="button"],input[type="image"],img[onclick]')].filter(e=>visible(e)&&norm(label(e))==='次へ');
    candidates=candidates.filter(e=>!candidates.some(other=>other!==e&&other.contains(e)));
    if(!candidates.length)throw Error('没有找到「次へ」。');
    // The screenshot contains both address-book pagination and the workflow next.
    // Use actual DOM positions, not fixed screen coordinates; workflow next is last.
    candidates.sort((a,b)=>b.getBoundingClientRect().top-a.getBoundingClientRect().top);
    if(candidates.length>1 && Math.abs(candidates[0].getBoundingClientRect().top-candidates[1].getBoundingClientRect().top)<8)throw Error('无法区分翻页与流程「次へ」，请手动处理。');
    document.querySelectorAll('[data-jp-ems-sender-next]').forEach(e=>e.removeAttribute('data-jp-ems-sender-next'));
    candidates[0].setAttribute('data-jp-ems-sender-next','true');
    return {ok:true};
  }catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={markSenderNext};
