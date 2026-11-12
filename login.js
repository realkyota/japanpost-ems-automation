function loginJapanPost(credentials, prepareOnly = false) {
  try {
    if(location.origin!=='https://www.int-mypage.post.japanpost.jp'||location.pathname!=='/mypage/M010000.do')throw Error('请先打开官方 M010000.do 登录页。');
    const visible=e=>e.getClientRects().length&&!e.disabled&&!e.readOnly;
    const one=(items,label)=>{if(items.length!==1)throw Error('无法唯一识别'+label+'，未填写登录信息。');return items[0];};
    const password=one([...document.querySelectorAll('input[type="password"]')].filter(visible),'密码框');
    const form=password.form;
    if(!form||new URL(form.action,location.href).origin!==location.origin)throw Error('登录表单地址不匹配，已停止。');
    const user=one([...form.querySelectorAll('input:not([type]),input[type="text"],input[type="email"]')].filter(visible),'登录账号框');
    const norm=s=>(s||'').replace(/\s/g,'').toLowerCase();
    const buttons=[...form.querySelectorAll('button,input[type="submit"],input[type="button"],input[type="image"],a')].filter(visible);
    const login=one(buttons.filter(el=>{
      const text=el.getAttribute('aria-label')||el.getAttribute('alt')||(el.tagName==='INPUT'?el.value:el.textContent?.trim())||el.querySelector('img')?.getAttribute('alt');
      return ['ログイン','login','ログインする','登入','登录'].includes(norm(text));
    }),'登录按钮');
    for(const attribute of ['formaction','href']) {
      const target=login.getAttribute(attribute);
      if(!target)continue;
      // URL schemes are case insensitive. Legacy sites commonly use JavaScript:.
      // Such an anchor invokes the site's existing handler; it is not an outside origin.
      const destination=new URL(target,location.href);
      if(attribute==='href' && destination.protocol==='javascript:')continue;
      if(destination.origin!==location.origin || !['https:','http:'].includes(destination.protocol)){
        const host=destination.hostname||'无网站主机';
        throw Error('登录按钮目标不匹配（'+attribute+'，协议 '+destination.protocol+'，主机 '+host+'），已停止；请将此错误文字发回。');
      }
    }
    if(!credentials.username||!credentials.password)throw Error('请填写登录账号和密码。');
    const old=[user.value,password.value];
    for(const [i,el] of [user,password].entries()){
      const value=i?credentials.password:credentials.username;
      if(el.maxLength>=0&&value.length>el.maxLength)throw Error('账号或密码超过官网长度限制。');
    }
    for(const [el,value] of [[user,credentials.username],[password,credentials.password]]) {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,value);
      el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
    }
    if(user.value!==credentials.username||password.value!==credentials.password||!user.checkValidity()||!password.checkValidity()){
      user.value=old[0];password.value=old[1];throw Error('官网未接受账号格式或输入值，请直接在官网登录；若要求邮箱，请使用注册邮箱。');
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
      return {ok:true,targetTag:clickTarget.tagName,message:'已定位登录控件，等待 Playwright 实际点击。'};
    }
    login.click();return {ok:true,message:'已点击官网登录按钮，请查看登录结果。若出现验证码或验证步骤，请在官网完成。'};
  } catch(e){return {ok:false,message:e.message};}
}
if(typeof module!=='undefined')module.exports={loginJapanPost};
