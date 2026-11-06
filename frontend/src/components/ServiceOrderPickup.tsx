import { useId } from 'react'
import { dateTime } from './saleMoney'
import './ServiceOrderPickup.css'

type Props = {
  phone?:string|null
  storeName:string
  notice?:{created_at:string;creator_username:string}|null
  onRecord?:()=>void
  disabled:boolean
}

export default function ServiceOrderPickup({phone,storeName,notice,onRecord,disabled}:Props) {
  const title = useId()
  const message = `Olá! Aqui é da ${storeName}. Seu pedido está pronto para retirada. Podemos combinar o melhor horário por aqui?`
  return <section className="os-pickup" aria-labelledby={title}>
    <div>
      <h3 id={title}>Aviso de retirada</h3>
      {notice
        ? <p><strong>Cliente avisado</strong> em {dateTime.format(new Date(notice.created_at))} · {notice.creator_username}</p>
        : <p>Nenhum contato registrado neste ciclo de retirada.</p>}
      {phone ? <p>WhatsApp cadastrado: <strong>+{phone}</strong>. Confira o número antes de abrir a conversa.</p>
        : phone===null && <p>Informe um WhatsApp válido com DDD no cadastro do cliente ativo para preparar o aviso.</p>}
    </div>
    {(phone||onRecord)&&<div className="os-pickup-action">
      {phone&&<a href={`https://wa.me/${phone}?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">Avisar retirada pelo WhatsApp</a>}
      {onRecord&&<button type="button" disabled={disabled} onClick={onRecord}>Marcar como avisado</button>}
      <small>{onRecord?'Registre somente depois de avisar o cliente.': 'O texto abre pronto para revisar e enviar no WhatsApp.'}</small>
    </div>}
  </section>
}
