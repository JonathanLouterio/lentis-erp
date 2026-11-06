import { useId } from 'react'
import type { PickupContactEvent } from '../api'
import { dateTime } from './saleMoney'
import './ServiceOrderPickup.css'

type Props = {
  phone?:string|null
  storeName:string
  notice?:PickupContactEvent|null
  reminder?:PickupContactEvent|null
  reminderDue:boolean
  reminderAvailableAt?:string|null
  onRecord?:()=>void
  onRecordReminder?:()=>void
  disabled:boolean
}

export default function ServiceOrderPickup({
  phone, storeName, notice, reminder, reminderDue, reminderAvailableAt, onRecord, onRecordReminder, disabled,
}:Props) {
  const title = useId()
  const needsContact = !notice || reminderDue
  const message = reminderDue
    ? `Olá! Aqui é da ${storeName}. Passando para lembrar que seu pedido continua disponível para retirada. Quer combinar um horário por aqui?`
    : `Olá! Aqui é da ${storeName}. Seu pedido está pronto para retirada. Podemos combinar o melhor horário por aqui?`
  const record = reminderDue ? onRecordReminder : onRecord
  return <section className="os-pickup" aria-labelledby={title}>
    <div>
      <h3 id={title}>Aviso de retirada</h3>
      {notice
        ? <p><strong>Cliente avisado</strong> em {dateTime.format(new Date(notice.created_at))} · {notice.creator_username}</p>
        : <p>Nenhum contato registrado neste ciclo de retirada.</p>}
      {reminder && <p><strong>Lembrete registrado</strong> em {dateTime.format(new Date(reminder.created_at))} · {reminder.creator_username}</p>}
      {reminderDue && <p><strong>Lembrete pendente.</strong> O pedido continua pronto para retirada.</p>}
      {!reminderDue && reminderAvailableAt && <p>Lembrete disponível a partir de {dateTime.format(new Date(reminderAvailableAt))}.</p>}
      {needsContact && (phone
        ? <p>WhatsApp cadastrado: <strong>+{phone}</strong>. Confira o número antes de abrir a conversa.</p>
        : phone===null && <p>Informe um WhatsApp válido com DDD no cadastro do cliente ativo para preparar a mensagem.</p>)}
    </div>
    {needsContact && (phone||record) && <div className="os-pickup-action">
      {phone && <a href={`https://wa.me/${phone}?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">
        {reminderDue?'Abrir lembrete no WhatsApp':'Avisar retirada pelo WhatsApp'}
      </a>}
      {record && <button type="button" disabled={disabled} onClick={record}>
        {reminderDue?'Registrar lembrete enviado':'Marcar como avisado'}
      </button>}
      <small>{record?'Registre somente depois de falar com o cliente.':'O texto abre pronto para revisar e enviar no WhatsApp.'}</small>
    </div>}
  </section>
}
