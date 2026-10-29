import {computed,inject,provide,type ComputedRef,type InjectionKey} from 'vue'

export type InputContext={courseId?:string;page?:number;language?:string;context?:Record<string,unknown>}
const key:InjectionKey<ComputedRef<InputContext>>=Symbol('input-assistance-context')
export function provideInputContext(value:()=>InputContext){provide(key,computed(value))}
export function useInputContext(){return inject(key,computed<InputContext>(()=>({})))}
