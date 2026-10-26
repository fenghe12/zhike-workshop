type Draft={form:Record<string,any>;files:Record<string,File|undefined>;updatedAt:number;taskId?:string}
function database():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{const request=indexedDB.open('smartcourse-drafts',1);request.onupgradeneeded=()=>request.result.createObjectStore('drafts');request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)})}
async function access<T>(owner:string,mode:IDBTransactionMode,operation:(store:IDBObjectStore)=>IDBRequest):Promise<T>{
 const db=await database()
 return new Promise((resolve,reject)=>{const transaction=db.transaction('drafts',mode);const request=operation(transaction.objectStore('drafts'));transaction.oncomplete=()=>{db.close();resolve(request.result as T)};transaction.onerror=()=>{db.close();reject(transaction.error)};transaction.onabort=()=>{db.close();reject(transaction.error)}})
}
export const loadDraft=(owner:string)=>access<Draft|undefined>(owner,'readonly',store=>store.get(owner))
export const saveDraft=(owner:string,value:Draft)=>access(owner,'readwrite',store=>store.put(value,owner))
export const deleteDraft=(owner:string)=>access(owner,'readwrite',store=>store.delete(owner))
