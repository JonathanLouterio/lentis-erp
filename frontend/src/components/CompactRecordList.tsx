import type { ReactNode } from 'react'
import './CompactRecordList.css'

export type CompactRecord = {
  id: number
  customer: string
  status: ReactNode
  fields: {label: string; value: ReactNode}[]
  note?: ReactNode
}

type Props = {
  label: string
  recordName: string
  action: string
  records: CompactRecord[]
  disabled: boolean
  onOpen: (id: number) => void
  selectedId?: number
}

export default function CompactRecordList({label,recordName,action,records,disabled,onOpen,selectedId}:Props){
  return <ul className="erp-compact-record-list" aria-label={label} role="list">
    {records.map(record=><li className={record.id===selectedId?'is-selected':undefined} key={record.id}>
      <div className="erp-compact-record-heading">
        <div className="erp-compact-record-person">
          <span>{recordName} #{record.id}</span>
          <strong>{record.customer}</strong>
        </div>
        <div className="erp-compact-record-status">{record.status}</div>
      </div>
      <dl className="erp-compact-record-fields">
        {record.fields.map(field=><div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
      </dl>
      {record.note&&<div className="erp-compact-record-note">{record.note}</div>}
      <button type="button" className="erp-secondary-button erp-compact-record-action"
        aria-label={`${action} ${record.id}`} disabled={disabled} onClick={()=>onOpen(record.id)}>
        {action}
      </button>
    </li>)}
  </ul>
}
