"""Autorização na fronteira HTTP; funções de domínio mantêm suas regras comerciais."""
from rest_framework.permissions import BasePermission
from rest_framework import serializers
from organizations.access_permissions import fresh_actor

ACTIONS = ('view', 'add', 'change', 'finalize', 'cancel')


def sale_capabilities(user):
    return {action: bool(user and user.has_perm(f'sales.{action}_sale')) for action in ACTIONS}


class SaleActionPermission(BasePermission):
    message = 'Você não tem permissão para esta ação de venda. Solicite a liberação ao administrador.'

    def has_permission(self, request, view):
        user = fresh_actor(request)
        if user is None:
            return False
        request.user = user  # As regras de domínio recebem os flags e permissões atuais.
        mapping = getattr(view, 'sale_actions', {})
        method = request.method
        if method == 'HEAD':
            method = 'GET'
        if method == 'OPTIONS':
            return any(sale_capabilities(user).values())
        actions = mapping.get(method)
        if actions is None:
            return True  # A própria API mantém o 405 para verbos não implementados.
        if actions == 'checkout':
            if not isinstance(request.data, dict):
                raise serializers.ValidationError('Envie um objeto JSON com os dados da venda.')
            # Valida discriminadores ANTES de qualquer replay ou escrita.
            sale_id = serializers.IntegerField(required=False, allow_null=True, min_value=1,
                max_value=9223372036854775807).run_validation(request.data.get('sale_id'))
            action = serializers.ChoiceField(choices=['draft', 'complete']).run_validation(request.data.get('action'))
            actions = ['change' if sale_id is not None else 'add']
            if action == 'complete':
                actions.append('finalize')
        if actions == 'any':
            return any(sale_capabilities(user).values())
        return all(user.has_perm(f'sales.{action}_sale') for action in actions)
