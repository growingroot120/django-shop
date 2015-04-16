# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.contrib.auth import get_user_model
from django.forms import fields
from django.forms import widgets
from django.utils.translation import ugettext_lazy as _
from djangular.styling.bootstrap3.forms import Bootstrap3ModelForm
from djangular.styling.bootstrap3.widgets import RadioSelect, RadioFieldRenderer, CheckboxInput
from shop.models.auth import get_customer
from shop.models.address import AddressModel
from shop.modifiers.pool import cart_modifiers_pool
from .base import DialogForm, DialogModelForm


class CustomerForm(DialogModelForm):
    scope_prefix = 'data.customer'

    class Meta:
        model = get_user_model()
        exclude = ('username', 'password', 'last_login', 'is_superuser', 'is_staff', 'is_active',
            'is_registered', 'groups', 'user_permissions', 'date_joined',)

    @classmethod
    def form_factory(cls, request, data, cart):
        user = get_customer(request)
        customer_form = cls(data=data, instance=user)
        if customer_form.is_valid():
            customer_form.save()
        else:
            return {cls.form_name: customer_form.errors}


class AddressForm(DialogModelForm):
    field_css_classes = {
        '*': getattr(Bootstrap3ModelForm, 'field_css_classes'),
        'zip_code': ['form-group', 'frmgrp-zip_code'],
        'location': ['form-group', 'frmgrp-location'],
    }

    priority = fields.IntegerField(widget=widgets.HiddenInput())  # TODO: use a choice field for selection

    class Meta:
        model = AddressModel
        exclude = ('user', 'priority_shipping', 'priority_invoice',)

    def __init__(self, initial=None, instance=None, *args, **kwargs):
        if instance:
            initial = initial or {}
            initial['priority'] = getattr(instance, self.priority_field)
        super(AddressForm, self).__init__(initial=initial, instance=instance, *args, **kwargs)

    @classmethod
    def get_model(cls):
        return cls.Meta.model

    @classmethod
    def form_factory(cls, request, data, cart):
        """
        From the given request, update the database model.
        If the form data is invalid, return an error dictionary to update the response.
        """
        # search for the associated address DB instance or create a new one
        priority = data and data.get('priority') or 0
        user = get_customer(request)
        filter_args = {'user': user, cls.priority_field: priority}
        instance = cls.Meta.model.objects.filter(**filter_args).first()
        address_form = cls(data=data, instance=instance)
        if address_form.is_valid():
            if not instance:
                instance = address_form.save(commit=False)
                instance.user = user
                setattr(instance, cls.priority_field, priority)
            assert address_form.instance == instance
            instance.save()
            cls.set_address(cart, instance)
        else:
            return {address_form.form_name: dict(address_form.errors)}


class ShippingAddressForm(AddressForm):
    scope_prefix = 'data.shipping_address'
    priority_field = 'priority_shipping'

    class Meta(AddressForm.Meta):
        widgets = {
            'country': widgets.Select(attrs={'ng-change': 'update()'}),
        }

    @classmethod
    def set_address(cls, cart, address):
        cart.shipping_address = address


class InvoiceAddressForm(AddressForm):
    scope_prefix = 'data.invoice_address'
    priority_field = 'priority_invoice'

    use_shipping_address = fields.BooleanField(required=False, initial=True,
        widget=CheckboxInput(_("Use shipping address for invoice")))

    def as_div(self):
        # Intentionally rendered without field `use_shipping_address`
        self.fields.pop('use_shipping_address', None)
        return super(InvoiceAddressForm, self).as_div()

    @classmethod
    def form_factory(cls, request, data, cart):
        """
        Overridden method to reuse data from ShippingAddressForm in case the checkbox for
        `use_shipping_address` is active.
        """
        if data and data.pop('use_shipping_address', False):
            scope_prefix = cls.scope_prefix.split('.', 1)[1]
            data = request.data.get(scope_prefix)
        return super(InvoiceAddressForm, cls).form_factory(request, data, cart)

    @classmethod
    def set_address(cls, cart, address):
        cart.invoice_address = address


class PaymentMethodForm(DialogForm):
    scope_prefix = 'data.payment_method'

    modifier = fields.ChoiceField(
        choices=[m.get_choice() for m in cart_modifiers_pool.get_payment_modifiers()],
        widget=RadioSelect(renderer=RadioFieldRenderer, attrs={'ng-change': 'update()'})
    )

    @classmethod
    def form_factory(cls, request, data, cart):
        cart.payment_method = data


class ShippingMethodForm(DialogForm):
    scope_prefix = 'data.shipping_method'

    modifier = fields.ChoiceField(
        choices=[m.get_choice() for m in cart_modifiers_pool.get_shipping_modifiers()],
        widget=RadioSelect(renderer=RadioFieldRenderer, attrs={'ng-change': 'update()'})
    )

    @classmethod
    def form_factory(cls, request, data, cart):
        cart.shipping_method = data


class ExtrasForm(DialogForm):
    scope_prefix = 'data.extras'

    annotation = fields.CharField(required=False, widget=widgets.Textarea)

    @classmethod
    def form_factory(cls, request, data, cart):
        cart.extras = cart.extras or {}
        cart.extras.update(data or {})


class TermsAndConditionsForm(DialogForm):
    scope_prefix = 'data.terms_and_conditions'

    accept = fields.BooleanField(required=True,
        widget=CheckboxInput(_("Accept terms and conditions.")))

    @classmethod
    def form_factory(cls, request, data, cart):
        data = data or {'accept': False}
        accept_form = cls(data=data)
        if not accept_form.is_valid():
            return {accept_form.form_name: dict(accept_form.errors)}
