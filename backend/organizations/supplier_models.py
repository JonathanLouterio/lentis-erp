import re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

STATES = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()


def normalize_document(value):
    value = (value or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9. /\-\t]*', value):
        raise ValidationError({'document': 'Use somente letras e números do documento, com ou sem pontuação.'})
    return re.sub(r'[. /\-\t]', '', value).upper()


def valid_document(value, person_type):
    if person_type == 'individual':
        if not re.fullmatch(r'[0-9]{11}',value) or len(set(value))==1:
            return False
        for length in (9,10):
            digit=(sum(int(value[i])*(length+1-i) for i in range(length))*10)%11
            if (0 if digit==10 else digit) != int(value[length]):return False
        return True
    # RFB: 12 caracteres ASCII alfanuméricos + 2 DVs numéricos; valor ASCII - 48.
    # https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}',value) or len(set(value))==1:
        return False
    for length,weights in ((12,(5,4,3,2,9,8,7,6,5,4,3,2)),(13,(6,5,4,3,2,9,8,7,6,5,4,3,2))):
        remainder=sum((ord(char)-48)*weight for char,weight in zip(value[:length],weights))%11
        if (0 if remainder<2 else 11-remainder) != int(value[length]):return False
    return True


class Supplier(models.Model):
    class PersonType(models.TextChoices):
        COMPANY='company','Pessoa jurídica'
        INDIVIDUAL='individual','Pessoa física'

    store=models.ForeignKey('organizations.Store',on_delete=models.PROTECT,related_name='suppliers',verbose_name='Unidade')
    person_type=models.CharField('Tipo de pessoa',max_length=10,choices=PersonType.choices,default=PersonType.COMPANY)
    name=models.CharField('Nome / razão social',max_length=180)
    trade_name=models.CharField('Nome fantasia',max_length=180,blank=True)
    document=models.CharField('CPF / CNPJ',max_length=32,blank=True)
    state_registration=models.CharField('Inscrição estadual / RG',max_length=30,blank=True)
    contact_name=models.CharField('Pessoa de contato',max_length=150,blank=True)
    phone=models.CharField('Telefone',max_length=30,blank=True)
    whatsapp=models.CharField('WhatsApp',max_length=30,blank=True)
    email=models.EmailField('E-mail',blank=True)
    zip_code=models.CharField('CEP',max_length=9,blank=True)
    street=models.CharField('Logradouro',max_length=150,blank=True)
    address_number=models.CharField('Número',max_length=20,blank=True)
    address_complement=models.CharField('Complemento',max_length=100,blank=True)
    neighborhood=models.CharField('Bairro',max_length=100,blank=True)
    city=models.CharField('Cidade',max_length=100,blank=True)
    state=models.CharField('UF',max_length=2,blank=True)
    notes=models.TextField('Observações',max_length=4000,blank=True)
    is_active=models.BooleanField('Ativo',default=True)
    version=models.PositiveIntegerField(default=1,editable=False)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name='Fornecedor'
        verbose_name_plural='Fornecedores'
        ordering=['name','pk']
        permissions=[('archive_supplier','Inativar fornecedor'),('restore_supplier','Reativar fornecedor')]
        constraints=[models.UniqueConstraint(fields=['store','document'],condition=~models.Q(document=''),name='unique_supplier_document_per_store'),models.CheckConstraint(condition=models.Q(version__gte=1),name='supplier_version_positive')]

    def clean(self):
        super().clean()
        self.name=self.name.strip()
        self.document=normalize_document(self.document)
        self.state=self.state.strip().upper()
        self.zip_code=self.zip_code.strip()
        errors={}
        if not self.name:errors['name']='Informe o nome ou razão social.'
        if self.document and not valid_document(self.document,self.person_type):errors['document']='Informe um CPF válido.' if self.person_type=='individual' else 'Informe um CNPJ válido (numérico ou alfanumérico).'
        if self.state and self.state not in STATES:errors['state']='Informe uma UF brasileira válida.'
        if self.zip_code:
            if not re.fullmatch(r'[0-9]{5}-?[0-9]{3}',self.zip_code):errors['zip_code']='Informe o CEP com 8 números.'
            else:self.zip_code=self.zip_code.replace('-','')
        if errors:raise ValidationError(errors)

    def save(self,*args,_service=False,**kwargs):
        if not _service:raise ValidationError('Use o cadastro de fornecedores do sistema para preservar a versão e o histórico.')
        if not self._state.adding:
            previous=type(self).objects.get(pk=self.pk)
            if self.store_id!=previous.store_id or self.created_by_id!=previous.created_by_id:
                raise ValidationError('A unidade e o autor do fornecedor não podem ser alterados.')
        self.full_clean()
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise ValidationError('Inative o fornecedor para preservar seus vínculos.')

    def __str__(self):return self.name


class SupplierEvent(models.Model):
    supplier=models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name='events')
    version=models.PositiveIntegerField()
    action=models.CharField(max_length=12,choices=[('create','Cadastro'),('update','Edição'),('archive','Inativação'),('restore','Reativação')])
    reason=models.CharField(max_length=255,blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-version']
        constraints=[models.UniqueConstraint(fields=['supplier','version'],name='unique_supplier_event_version')]

    def save(self,*args,**kwargs):
        if not self._state.adding:raise ValidationError('Eventos de fornecedor não podem ser alterados.')
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):raise ValidationError('Eventos de fornecedor não podem ser excluídos.')


class SupplierOperation(models.Model):
    request_id=models.UUIDField(unique=True)
    supplier=models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name='+')
    digest=models.CharField(max_length=64)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    created_at=models.DateTimeField(auto_now_add=True)
