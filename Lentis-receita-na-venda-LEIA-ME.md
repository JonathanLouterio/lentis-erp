# Lentis ERP — Receita vinculada à venda

Pacote baseado nos seis arquivos de vendas enviados em 19/10/2026 e na versão de api.ts entregue no módulo de receitas. Requer o módulo de receitas oftalmológicas já instalado. Arquivos completos UTF-8, preservando a estrutura backend/frontend. Não há nova dependência.

## Instalar

Pare os servidores com Ctrl+C. Confira a branch:

```powershell
cd C:\Projetos\lentis-erp
git branch --show-current
git status --short
```

A branch desta etapa é feat/receita-na-venda. Se ainda estiver na main e não a criou:

```powershell
git switch -c feat/receita-na-venda
```

Extraia o ZIP em C:\Projetos\lentis-erp, substituindo os arquivos correspondentes e mantendo as pastas backend e frontend. Não mantenha backups .tsx dentro de src.

Com .venv ativa e PostgreSQL em execução:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py makemigrations sales
python backend\manage.py migrate
python backend\manage.py check
python backend\manage.py test organizations sales --verbosity 2
cd frontend
npm run build
```

É esperado criar SalePrescription e adicionar prescription_record à venda. O campo novo é opcional: vendas anteriores não precisam ser preenchidas. A migração terá a numeração compatível com seu histórico e deve entrar no commit desta etapa.

Reinicie os servidores, cada um em um terminal:

```powershell
cd C:\Projetos\lentis-erp
python backend\manage.py runserver 127.0.0.1:8000
```

```powershell
cd C:\Projetos\lentis-erp\frontend
npm run dev
```

## Teste na tela

1. Em Cadastros → Receitas, cadastre uma receita para um cliente da unidade.
2. Em Comercial → Vendas, crie uma venda e selecione esse cliente.
3. No bloco Receita do atendimento, selecione a receita. Confira os dados da versão escolhida.
4. Adicione os produtos e clique em Salvar rascunho. A cópia deve aparecer como Cópia salva, com operador e data.
5. Em outra aba, corrija a receita original com motivo. Na venda, clique em Atualizar opções de receitas: a cópia salva deve manter os dados anteriores. Se a versão nova estiver nas opções carregadas, a tela avisa que o cadastro possui outra versão.
6. Para usar os dados novos, escolha explicitamente essa nova versão no rascunho e salve. Consulte o histórico da receita na venda: as cópias anteriores continuam preservadas.
7. Configure o pagamento e conclua. A versão usada permanece na venda e não pode ser trocada após a conclusão. Cancelar também não apaga a cópia.
8. Em outro rascunho, selecione Remover vínculo ao salvar. O vínculo atual é removido, mas o histórico continua disponível.

A escolha também pode ser feita na primeira conclusão da venda, sem salvar um rascunho antes. O vínculo e o atendimento são registrados na mesma transação.

## Permissões

Use seu superusuário ativo no primeiro teste. Usuários comuns precisam de organizations.view_prescription e vínculo ativo com a unidade para consultar/selecionar receitas. É a mesma permissão do módulo anterior; não há permissão nova para configurar.

Sem essa permissão, a venda continua disponível, mas os graus não são retornados e não é possível escolher/remover a receita. Alterar o cliente de uma venda já vinculada exige que alguém autorizado remova ou substitua o vínculo, preservando a consistência do atendimento.

Receitas de outro cliente/unidade, versões desatualizadas e receitas arquivadas não podem ser escolhidas como um novo vínculo. Uma cópia anteriormente salva permanece histórica, mesmo se a origem for arquivada depois.

## Resposta de rede incerta e edições simultâneas

Se o envio perder a resposta, use Repetir envio com segurança. A mesma identificação de checkout recupera a venda sem duplicar a cópia ou as movimentações.

Se outra pessoa mudou o vínculo enquanto a venda estava aberta, o sistema pede para reabrir a venda antes de substituir a escolha. Não atualiza os graus automaticamente.

## Validação local

13 testes novos de API passaram no ambiente isolado SQLite. Há também um teste de seleção concorrente para PostgreSQL, ignorado no SQLite. Regressão completa: 280 testes, sem falhas; 269 passaram e 11 que dependem de bloqueios de banco foram ignorados. Execute a suíte acima no seu PostgreSQL.

Build TypeScript/Vite aprovado. Fluxo real React + Django conferido no navegador: escolha da receita, cópia no rascunho, resposta perdida com recuperação sem duplicação, correção da origem mantendo a cópia, aviso de versão diferente, recebimento Pix confirmado e baixa de estoque na conclusão, histórico e tema escuro em celular sem rolagem horizontal.

## Arquivos completos incluídos

Backend em sales: models.py, serializers.py, payment_serializers.py, payment_services.py, urls.py, prescription_models.py, prescription_services.py, prescription_views.py e test_sale_prescription.py.

Frontend: src/api.ts, src/components/Sales.tsx e src/components/SalePrescriptionPanel.tsx. Reutiliza Prescriptions.css do módulo anterior.

Documentação: docs/regras-negocio.md e este guia.

Não inclui os arquivos auxiliares da raiz nem altera a logo. A migração gerada por makemigrations sales será um arquivo adicional no seu projeto.
