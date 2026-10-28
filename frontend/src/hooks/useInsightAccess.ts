import { useEffect, useState } from 'react'
import { getInsightAccess } from '../api'
import type { InsightAccess } from '../api'

export function useInsightAccess(storeId:number,reload:number){
  const [access,setAccess]=useState<InsightAccess|null>(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)
  useEffect(()=>{
    if(storeId<1){setAccess(null);setLoading(false);return}
    let ignore=false
    async function refresh(){
      setLoading(true)
      try{const next=await getInsightAccess(storeId);if(!ignore){setAccess(next);setError('')}}
      catch(err){if(!ignore){setAccess(null);setError(err instanceof Error?err.message:'Não foi possível conferir os acessos.')}}
      finally{if(!ignore)setLoading(false)}
    }
    void refresh();window.addEventListener('focus',refresh)
    return()=>{ignore=true;window.removeEventListener('focus',refresh)}
  },[storeId,reload])
  return {access:access?.store_id===storeId?access:null,error,loading}
}
