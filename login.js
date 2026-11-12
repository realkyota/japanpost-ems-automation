function loginJapanPost(credentials, prepareOnly = false) {
  try {
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp'||location.pathname!=='/mypage/M010000.do')throw Error('Open the official M010000.do login page first.');
    const visible=e=>e.getClientRects().length&&!e.disabled&&!e.readOnly;
    const one=(items,label)=>{if(items.length!==1)throw Error('Cannot uniquely identify '+label+'; credentials not filled.');return items[0];};
    const password=one([...document.querySelectorAll('input[type="password"]')].filter(visible),'password field');
    const form=password.form;
    if(!form||new URL(form.action,location.href).origin!==location.origin)throw Error('Login form destination mismatch; stopped.');
    const user=one([...form.querySelectorAll('input:not([type]),input[type="text"],input[type="email"]')].filter(visible),'username field');
    const norm=s=>(s||'').replace(/\s/g,'').toLowerCase();
    const buttons=[...form.querySelectorAll('button,input[type="submit"],input[type="button"],input[type="image"],a')].filter(visible);
    const login=one(buttons.filter(el=>{
      const text=el.getAttribute('aria-label')||el.getAttribute('alt')||(el.tagName==='INPUT'?el.value:el.textContent?.trim())||el.querySelector('img')?.getAttribute('alt');
      return ['ログイン','login','ログインする','登入','登录'].includes(norm(text));
    }),'login control');
    for(const attribute of ['formaction','href']) {
      const target=login.getAttribute(attribute);
      if(!target)continue;
      // URL schemes are case insensitive. Legacy sites commonly use JavaScript:.
      // Such an anchor invokes the site's existing handler; it is not an outside origin.
      const destination=new URL(target,location.href);
      if(attribute==='href' && destination.protocol==='javascript:')continue;
      if(destination.origin!==location.origin || !['https:','http:'].includes(destination.protocol)){
        const host=destination.hostname||'no hostname';
        throw Error('Login control destination mismatch ('+attribute+', scheme '+destination.protocol+', host '+host+'); stopped. Report this error message.');
      }
    }
    if(!credentials.username||!credentials.password)throw Error('Supply username and password.');
    const old=[user.value,password.value];
    for(const [i,el] of [user,password].entries()){
      const value=i?credentials.password:credentials.username;
      if(el.maxLength>=0&&value.length>el.maxLength)throw Error('Username or password exceeds the website length limit.');
    }
    for(const [el,value] of [[user,credentials.username],[password,credentials.password]]) {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);
      el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
    }
    if(user.value!==credentials.username||password.value!==credentials.password||!user.checkValidity()||!password.checkValidity()){
      user.value=old[0];password.value=old[1];throw Error('Website rejected the input. Log in manually; use your registered email if required.');
    }
    if(prepareOnly){
      for(const attribute of ['data-jp-login-user','data-jp-login-password','data-jp-login-button']){
        document.querySelectorAll('['+attribute+']').forEach(el=>el.removeAttribute(attribute));
      }
      user.setAttribute('data-jp-login-user','true');
      password.setAttribute('data-jp-login-password','true');
      const image=login.querySelector('img,input[type="image"]');
      const clickTarget=image&&visible(image)?image:login;
      clickTarget.setAttribute('data-jp-login-button','true');
      return {ok:true,targetTag:clickTarget.tagName,message:'Login control located; waiting for the Playwright click.'};
    }
    login.click();return {ok:true,message:'Clicked login. Check the result and complete website verification if prompted.'};
  } catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={loginJapanPost};
