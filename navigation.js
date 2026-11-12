function markSenderNext() {
  try {
    const norm=s=>(s||'').normalize('NFKC').replace(/\s/g,'');
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp'||!norm(document.body?.innerText||'').includes('ご依頼主を選択する'))throw Error('Not on the sender selection page.');
    const visible=e=>e.getClientRects().length&&!e.disabled;
    const selected=[...document.querySelectorAll('input[type="radio"]')].filter(e=>visible(e)&&e.checked);
    if(selected.length!==1)throw Error('Cannot identify exactly one selected sender. Select it on the website; the program will not change the sender.');
    const label=e=>e.getAttribute('aria-label')||e.getAttribute('alt')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';
    let candidates=[...document.querySelectorAll('button,a,input[type="submit"],input[type="button"],input[type="image"],img[onclick]')].filter(e=>visible(e)&&norm(label(e))==='次へ');
    candidates=candidates.filter(e=>!candidates.some(other=>other!==e&&other.contains(e)));
    if(!candidates.length)throw Error('Cannot find 「次へ」.');
    // The screenshot contains both address-book pagination and the workflow next.
    // Use actual DOM positions, not fixed screen coordinates; workflow next is last.
    candidates.sort((a,b)=>b.getBoundingClientRect().top-a.getBoundingClientRect().top);
    if(candidates.length>1 && Math.abs(candidates[0].getBoundingClientRect().top-candidates[1].getBoundingClientRect().top)<8)throw Error('Cannot distinguish pagination from workflow 「次へ」; handle manually.');
    document.querySelectorAll('[data-jp-ems-sender-next]').forEach(e=>e.removeAttribute('data-jp-ems-sender-next'));
    candidates[0].setAttribute('data-jp-ems-sender-next','true');
    return {ok:true};
  }catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={markSenderNext};
