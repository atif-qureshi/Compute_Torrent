export type Recipe = {model_id:string;revision:string;prompt:string;max_new_tokens:number;min_peers:number;max_peers:number;benchmark:boolean}
export const initialRecipe:Recipe={model_id:'',revision:'main',prompt:'',max_new_tokens:32,min_peers:2,max_peers:4,benchmark:true}
export function validateRecipe(value:any,catalog:any[]):Recipe {
 if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('The recipe must be an object with named fields.')
 const allowed=['model_id','revision','prompt','max_new_tokens','min_peers','max_peers','benchmark','layers','hidden_size','label','weights_bytes']
 if(Object.keys(value).some(k=>!allowed.includes(k)))throw new Error('The recipe contains unsupported fields. Use the downloadable example.')
 const r={...initialRecipe,min_peers:1,max_peers:8,...value}
 if(!catalog.some(m=>m.model_id===r.model_id))throw new Error('Select a model supported by the current coordinator catalog.')
 if(typeof r.prompt!=='string'||!r.prompt.trim()||r.prompt.length>4000)throw new Error('Enter a prompt between 1 and 4,000 characters.')
 if(typeof r.revision!=='string'||!/^main$|^[a-f0-9]{40}$/.test(r.revision))throw new Error('Revision must be main or a 40-character lowercase commit SHA.')
 for(const [key,min,max] of [['max_new_tokens',1,128],['min_peers',1,8],['max_peers',2,8]] as const){if(!Number.isInteger(r[key])||r[key]<min||r[key]>max)throw new Error(`${key} must be a whole number between ${min} and ${max}.`)}
 if(r.max_peers<r.min_peers)throw new Error('Maximum providers must be at least the minimum providers.')
 if(typeof r.benchmark!=='boolean')throw new Error('Benchmark must be true or false.')
 return {model_id:r.model_id,revision:r.revision,prompt:r.prompt.trim(),max_new_tokens:r.max_new_tokens,min_peers:r.min_peers,max_peers:r.max_peers,benchmark:r.benchmark}
}
export function parseRecipe(text:string,format:string,catalog:any[]):Recipe {
 if(new TextEncoder().encode(text).length>65536)throw new Error('Upload a recipe smaller than 64 KiB.')
 if(format==='json')return validateRecipe(JSON.parse(text),catalog)
 if(/<!DOCTYPE|<!ENTITY/i.test(text))throw new Error('XML DTDs and entities are not supported.')
 const doc=new DOMParser().parseFromString(text,'application/xml'),root=doc.documentElement
 if(doc.querySelector('parsererror')||root.tagName!=='inference'||root.attributes.length)throw new Error('Use a valid XML document with an <inference> root and no attributes.')
 const value:Record<string,any>={}
 for(const child of Array.from(root.children)){if(child.children.length||child.attributes.length||child.tagName in value)throw new Error('XML fields must be unique and flat, without attributes.');value[child.tagName]=child.textContent||''}
 for(const k of ['max_new_tokens','min_peers','max_peers'])if(k in value){if(!/^\d+$/.test(value[k].trim()))throw new Error(`${k} must be a whole number.`);value[k]=Number(value[k])}
 if('benchmark' in value){if(!/^(true|false)$/i.test(value.benchmark.trim()))throw new Error('Benchmark must be true or false.');value.benchmark=value.benchmark.trim().toLowerCase()==='true'}
 return validateRecipe(value,catalog)
}