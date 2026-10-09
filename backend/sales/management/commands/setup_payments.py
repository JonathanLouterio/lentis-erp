from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from organizations.models import Store
from sales.models import FinancialAccount, PaymentMethod


class Command(BaseCommand):
    help = "Cria formas e contas iniciais sem alterar os cadastros existentes."

    def add_arguments(self, parser):
        parser.add_argument("--store-id", type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        stores = Store.objects.filter(is_active=True, company__is_active=True)
        if options["store_id"]:
            stores = stores.filter(pk=options["store_id"])
        if not stores.exists():
            raise CommandError("Nenhuma unidade ativa foi encontrada.")
        for store in stores:
            for code, name in [("cash", "Caixa da loja"), ("bank", "Banco da loja")]:
                FinancialAccount.objects.get_or_create(store=store, code=code, defaults={"name": name})
            for kind, name in PaymentMethod.Kind.choices:
                PaymentMethod.objects.get_or_create(store=store, code=kind, defaults={"name": name, "kind": kind})
            self.stdout.write(self.style.SUCCESS(f"Pagamentos configurados para {store.name}."))
