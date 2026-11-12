const assert=require('node:assert/strict');
const {operateShipment}=require('./shipment.js');
global.location={origin:'https://www.int-mypage.post.japanpost.jp',pathname:'/dispatch'};
class Select{constructor(options){this.tagName='SELECT';this._value='old';this.options=options;this.isConnected=true;this.maxLength=-1}get value(){return this._value}set value(v){this._value=v}getClientRects(){return[1]}dispatchEvent(){}}
global.HTMLSelectElement=Select;
function run(options){const select=new Select(options);const row={querySelector:()=>({textContent:'発送予定日 必須'}),querySelectorAll:()=>[select]};global.document={body:{textContent:'発送関連情報登録'},querySelectorAll:selector=>selector==='tr'?[row]:[]};return {result:operateShipment({shipDate:'2026/11/13'},'dispatch'),select};}
let test=run([{value:'20261113',textContent:'2026/11/13（金）'}]);assert.equal(test.result.ok,true,test.result.message);assert.equal(test.select.value,'20261113');
test=run([{value:'date-13',textContent:'2026年11月13日（金）'}]);assert.equal(test.result.ok,true,test.result.message);assert.equal(test.select.value,'date-13');
test=run([{value:'20261112',textContent:'2026/11/12'}]);assert.equal(test.result.ok,false);assert.equal(test.select.value,'old');
test=run([{value:'a',textContent:'2026/11/13'},{value:'b',textContent:'2026/11/13'}]);assert.equal(test.result.ok,false);assert.equal(test.select.value,'old');
console.log('PASS: next-day dropdown with weekday/compact values/Japanese dates; missing or duplicate dates rejected.');
