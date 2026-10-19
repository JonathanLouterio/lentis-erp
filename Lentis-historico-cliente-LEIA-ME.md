# Lentis ERP — Histórico do cliente

## Instalação

Com a branch `feat/historico-cliente` ativa, extraia o ZIP na raiz `C:\Projetos\lentis-erp`, preservando as pastas backend, frontend e docs. Os arquivos estão em UTF-8 e partem da versão enviada após a integração de OS, main b4b1794.

Não há mudanças de modelos ou migrações nesta etapa. Não é necessário instalar novas dependências.

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py check
python backend\manage.py test organizations.test_customer_history --verbosity 2
cd frontend
npm run build
```

Se desejar executar a regressão completa do projeto:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py test organizations sales --verbosity 2
```

Reinicie o backend depois de substituir os arquivos. Na raiz: `python backend\manage.py runserver 127.0.0.1:8000`. Em outro terminal, dentro de frontend: `npm run dev`.

## Acesso

Cadastros → Clientes → **Histórico** na linha do cliente.

A tela mostra contato e endereço atuais, quantidade de vendas finalizadas/rascunhos, saldo a receber do cliente, valor vencido do cliente e saldo devido pela operadora. As parcelas de cartão da operadora não aparecem como dívida do cliente.

Use as abas Vendas, Orçamentos, Receitas, Ordens de serviço e Parcelas. Cada aba tem paginação e consulta de detalhes. **Abrir venda** navega ao atendimento existente; **Acompanhar OS** abre a ordem correspondente. Voltar aos clientes retorna à listagem.

Receitas exigem organizations.view_prescription; OS exigem sales.view_serviceorder. Usuários sem essas permissões veem as abas desabilitadas e não recebem contagens, registros ou valores clínicos dessas seções. As outras seções seguem o acesso por unidade já adotado nos módulos existentes.

A receita consultada nesta ficha é a versão atual do cadastro, podendo estar arquivada. As cópias utilizadas na venda e na OS ficam preservadas e são consultadas no atendimento de origem. Os históricos completos de versões, decisões, eventos e correções continuam nos seus módulos; esta tela reúne as fichas e seus detalhes principais.

## Teste manual

1. Abra o histórico de um cliente com vendas, receitas, orçamentos e OS; confira cada aba e detalhes.
2. Teste um cliente sem registros e confira o estado vazio sem erros.
3. Confira uma venda no crediário com pagamento parcial: o saldo deve diminuir exatamente pelo valor recebido.
4. Compare uma venda de cartão a receber da operadora: seu saldo não deve aumentar a dívida do cliente.
5. Cancele uma venda: ela continua no histórico, mas sua parcela não deve somar ao saldo pendente ou vencido.
6. Teste receitas com usuário autorizado e depois sem permissão. Ser staff ou ter permissão de OS não libera receitas.
7. Abra a venda/OS a partir do detalhe e confira que corresponde ao cliente e à unidade.
8. Troque a unidade: o histórico de um cliente da loja anterior deve ser recusado. Nenhum dado anterior deve permanecer visível.
9. Confira tema claro/escuro e tela de celular.

## API

GET `/api/me/customers/<customer_id>/history/?store_id=<id>` → resumo.

Parâmetros opcionais:
- `section=sales|quotes|prescriptions|orders|installments` → registros paginados.
- `page=1` → página (padrão 25 registros, limite 100 por página se page_size for usado).
- `record_id=<id>` com uma seção → detalhe validado para o mesmo cliente e unidade.

Métodos de alteração não são aceitos. Receitas e OS sem permissão retornam 403; registro de outro cliente/unidade autorizada retorna 404. Unidade inacessível segue o erro 400 existente do projeto.

## Arquivos do pacote

- backend/organizations/urls.py
- backend/organizations/customer_history_api.py
- backend/organizations/test_customer_history.py
- frontend/src/api.ts
- frontend/src/components/AppLayout.tsx
- frontend/src/components/CustomerHistory.tsx
- frontend/src/components/CustomerHistory.css
- docs/regras-negocio.md
- Este guia.

O arquivo backend/sales/urls.py enviado foi consultado para compatibilidade e não precisa ser substituído.
