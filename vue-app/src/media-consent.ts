import {t,policyText} from './ui-language'
export async function confirmMediaUse():Promise<{authorized:true;version:string}>{
 const response=await fetch('/v1/auth/policies')
 if(!response.ok)throw Error('素材处理说明暂时无法读取，请稍后重试。')
 const policy=await response.json()
 const approved=window.confirm(t('人物照片与声音使用授权')+'\n\n'+policy.documents.media.sections.map((x:any,index:number)=>t(x.title)+': '+policyText('media',index,x.text)).join('\n\n')+'\n\n'+t('我确认素材属于本人或已取得相应授权，同意将本次人物照片和参考音频用于上述处理。'))
 if(!approved)throw Error('尚未同意素材处理，文件未上传。')
 return {authorized:true,version:policy.mediaVersion}
}
