import { useId } from 'react'
import './ServiceOrderPickup.css'

type Props = {phone:string|null;storeName:string}

export default function ServiceOrderPickup({phone,storeName}:Props) {
  const title = useId()
  const message = `Olá! Aqui é da ${storeName}. Seu pedido está pronto para retirada. Podemos combinar o melhor horário por aqui?`
  return <section className="os-pickup" aria-labelledby={title}>
    <div>
      <h3 id={title}>Aviso de retirada</h3>
      {phone ? <p>WhatsApp cadastrado: <strong>+{phone}</strong>. Confira o número antes de abrir a conversa.</p>
        : <p>Informe um WhatsApp válido com DDD no cadastro do cliente ativo para preparar o aviso.</p>}
    </div>
    {phone && <div className="os-pickup-action">
      <a href={`https://wa.me/${phone}?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">Avisar retirada pelo WhatsApp</a>
      <small>O texto abre pronto para revisar e enviar no WhatsApp.</small>
    </div>}
  </section>
}
