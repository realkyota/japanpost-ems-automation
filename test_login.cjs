const assert=require('node:assert/strict');
const {loginJapanPost}=require('./login.js');
const origin='https://www.int-mypage.post.japanpost.jp';
global.location={origin,pathname:'/mypage/M010000.do',href:origin+'/mypage/M010000.do'};
class Input{constructor(){this._value='';this.maxLength=100}get value(){return this._value}set value(v){this._value=v}getClientRects(){return[1]}dispatchEvent(){}checkValidity(){return true}}
global.HTMLInputElement=Input;global.Event=class{};
const user=new Input(),password=new Input();let href='JavaScript:submitLogin();',formaction=null;
const button={tagName:'A',textContent:'ログイン',getAttribute:k=>k==='href'?href:k==='formaction'?formaction:null,getClientRects:()=>[1],querySelector:()=>null,click(){this.clicked=true}};
const form={action:origin+'/mypage/M010000.do',querySelectorAll:s=>s.startsWith('input:not')?[user]:[button]};password.form=form;
global.document={querySelectorAll:()=>[password]};
const credentials={username:'example@example.com',password:'FAKE_UNIT_TEST_PASSWORD'};
for(const link of ['JavaScript:submitLogin();','JAVASCRIPT:void(0)',' javascript:submitLogin()','#','/mypage/M010000.do']){
 href=link;button.clicked=false;const result=loginJapanPost(credentials);assert.equal(result.ok,true,link+': '+result.message);assert.equal(button.clicked,true);
}
for(const link of ['https://example.com/login','//example.com/login','mailto:example@example.com','data:text/html,example']){
 href=link;button.clicked=false;user.value='';password.value='';assert.equal(loginJapanPost(credentials).ok,false);assert.equal(button.clicked,false);assert.equal(password.value,'');
}
href='JavaScript:submitLogin()';formaction='https://example.com/login';button.clicked=false;assert.equal(loginJapanPost(credentials).ok,false);assert.equal(button.clicked,false);
console.log('PASS: JavaScript scheme capitalization/whitespace, same-origin links; external and non-web destinations blocked before credential entry.');
// Actual public login markup uses an image inside a JavaScript anchor.
Input.prototype.setAttribute=function(k,v){(this.attrs??={})[k]=v};
Input.prototype.removeAttribute=function(k){delete(this.attrs??={})[k]};
const loginImage={tagName:'IMG',attrs:{},getClientRects:()=>[1],setAttribute(k,v){this.attrs[k]=v}};
href="javaScript:submitCommand('login');";formaction=null;button.clicked=false;
button.querySelector=()=>loginImage;
global.document.querySelectorAll=selector=>selector==='input[type="password"]'?[password]:[];
const prepared=loginJapanPost(credentials,true);
assert.equal(prepared.ok,true);assert.equal(prepared.targetTag,'IMG');assert.equal(button.clicked,false);assert.equal(loginImage.attrs['data-jp-login-button'],'true');
console.log('PASS: prepare-only mode targets the actual child image without submitting.');
