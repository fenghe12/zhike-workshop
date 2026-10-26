import {api,post,ApiError} from './api'
type Status={id:string;size:number;chunkSize:number;count:number;received:number[];result?:any}
export async function resumableUpload(file:File,kind:string,owner:string,consent:any,onProgress:(percentage:number)=>void){
 const key='smartcourse-upload:'+owner+':'+JSON.stringify([kind,file.name,file.size,file.lastModified])
 let status:Status|undefined,id=localStorage.getItem(key)
 if(id){try{status=await api<Status>('/v1/uploads/resumable/'+id)}catch(e){if(!(e instanceof ApiError)||e.status!==404)throw e;localStorage.removeItem(key)}}
 if(!status){status=await post<Status>('/v1/uploads/resumable',{filename:file.name,size:file.size,kind,...(consent?{mediaConsent:consent}:{})});localStorage.setItem(key,status.id)}
 if(status.result){onProgress(100);return status.result}
 const identifier=status.id,received=new Set(status.received),chunkSize=status.chunkSize
 let completed=[...received].reduce((sum,index)=>sum+Math.min(chunkSize,file.size-index*chunkSize),0)
 onProgress(Math.round(completed/file.size*100))
 for(let index=0;index<status.count;index++){
  if(received.has(index))continue
  const piece=file.slice(index*chunkSize,Math.min(file.size,(index+1)*chunkSize))
  let succeeded=false
  for(let attempt=0;attempt<3&&!succeeded;attempt++){
   try{await new Promise<void>((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('PUT','/v1/uploads/resumable/'+identifier+'/parts/'+index);xhr.setRequestHeader('Content-Type','application/octet-stream')
    const token=sessionStorage.getItem('smartcourse-token');if(token)xhr.setRequestHeader('Authorization','Bearer '+token)
    xhr.timeout=60000;xhr.upload.onprogress=e=>onProgress(Math.round((completed+e.loaded)/file.size*100))
    xhr.onload=()=>{let data:any;try{data=JSON.parse(xhr.responseText)}catch{};if(xhr.status>=200&&xhr.status<300)resolve();else reject(new ApiError(data?.message||'上传已暂停，重新提交时将继续上传。',xhr.status))}
    xhr.onerror=xhr.ontimeout=()=>reject(Error('上传已暂停，重新提交时将继续上传。'));xhr.send(piece)
   });succeeded=true}catch(e){if(e instanceof ApiError&&e.status>=400&&e.status<500)throw e;if(attempt===2)throw e;await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)))}}
  completed+=piece.size;onProgress(Math.round(completed/file.size*100))
 }
 const result=await post<any>('/v1/uploads/resumable/'+identifier+'/complete',{})
 onProgress(100);return result
}
