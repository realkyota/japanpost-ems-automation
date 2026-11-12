const assert=require('node:assert/strict');
const {markEMSContent,markContentInputs}=require('./content.js');
global.location={origin:'https://www.int-mypage.post.japanpost.jp',pathname:'/mypage/M060800.do'};
function node(tag,text=''){return{tagName:tag,textContent:text,children:[],attrs:{},getClientRects:()=>[1],getAttribute(k){return this.attrs[k]||null},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},contains(other){return this.children.includes(other)},querySelector(){return null},closest(selector){return selector==='tr'?row:this},querySelectorAll(selector){if(selector==='select')return this.selects||[];if(selector.startsWith('input:not'))return this.inputs||[];return this.buttons||[];}}}
const docs=node('BUTTON','EMS（書類）'),goods=node('DIV','EMS（物品）または税関検査対象');
const name=node('INPUT'),price=node('INPUT'),weight=node('INPUT'),hs=node('INPUT'),quantity=node('INPUT');name.placeholder='内容品名';
const currency=node('SELECT'),origin=node('SELECT');currency.options=[{textContent:'JPY/円'}];origin.options=[{textContent:'JAPAN（日本）'}];
const confirm=node('BUTTON','確定');const cells=Array.from({length:5},()=>node('TD'));cells[0].inputs=[name];cells[1].inputs=[price];cells[1].selects=[currency,origin];cells[2].inputs=[weight,hs];cells[3].inputs=[quantity];cells[4].buttons=[confirm];
const row=node('TR');row.children=cells;
global.document={querySelectorAll(selector){if(selector==='tr')return[row];if(selector==='select')return[currency,origin];if(selector.startsWith('input:not'))return[name,price,weight,hs,quantity];if(selector.startsWith('[data-'))return[];return[docs,goods,confirm];}};
assert.equal(markEMSContent().ok,true);assert.equal(goods.attrs['data-jp-content-service'],'true');assert.equal(docs.attrs['data-jp-content-service'],undefined);
assert.equal(markContentInputs().ok,true);assert.equal(origin.attrs['data-jp-content-origin'],'true');assert.equal(confirm.attrs['data-jp-content-confirm'],'true');assert.equal(hs.attrs['data-jp-content-hsCode'],'true');
name.placeholder='';assert.equal(markContentInputs().ok,true);
console.log('PASS: EMS goods control, screenshot table fields, Japan dropdown marker, confirm marker, fallback without placeholders (mock DOM).');
const emsImage=node('IMG');emsImage.attrs.alt='EMS（物品）または税関検査対象';
const oldQuery=goods.querySelectorAll;
goods.querySelectorAll=function(selector){return selector.startsWith('img')?[emsImage]:oldQuery.call(this,selector)};
assert.equal(markEMSContent().ok,true);assert.equal(emsImage.attrs['data-jp-content-service'],'true');
console.log('PASS: EMS chooses the visible child image as the click target.');
// Reproduce a two-TR layout: origin and HS are not children of the first input row.
cells[1].selects=[currency];cells[2].inputs=[weight];
const originCell=node('TD'),hsCell=node('TD');originCell.selects=[origin];hsCell.inputs=[hs];
row.nextElementSibling=node('TR');row.nextElementSibling.children=[originCell,hsCell];
for(const el of [name,price,weight,hs,quantity,origin,confirm])el.attrs={};
let splitResult=markContentInputs();assert.equal(splitResult.ok,true,splitResult.message);assert.equal(hs.attrs['data-jp-content-hsCode'],'true');assert.equal(origin.attrs['data-jp-content-origin'],'true');
// The placeholder route must also work regardless of physical rows.
name.placeholder='内容品名';price.placeholder='単価';weight.placeholder='重量 g/個';hs.placeholder='HSコード';quantity.placeholder='個数';
splitResult=markContentInputs();assert.equal(splitResult.ok,true,splitResult.message);
console.log('PASS: rowspan/two-TR content layout, with and without placeholders.');
