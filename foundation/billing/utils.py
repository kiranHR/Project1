# -*- coding: utf-8 -*-
from datetime import datetime
from time import strftime

from django.conf import settings
from django.core.cache import cache
from django.db.models import get_model

from ikwen.foundation.core.models import Service

from ikwen.foundation.core.utils import get_service_instance
from django.utils.translation import gettext as _

from ikwen.foundation.billing.models import InvoicingConfig, Invoice, AbstractSubscription


def get_invoicing_config_instance(using='default'):
    service = get_service_instance(using)
    invoicing_config = cache.get(service.id + ':invoicing_config:' + using)
    if invoicing_config:
        return invoicing_config
    invoicing_config = InvoicingConfig.objects.using(using).all()[0]
    cache.set(service.id + ':invoicing_config:' + using, invoicing_config)
    return invoicing_config


def get_billing_cycle_days_count(billing_cycle):
    if billing_cycle == Service.MONTHLY:
        return 30
    if billing_cycle == Service.QUARTERLY:
        return 91
    if billing_cycle == Service.BI_ANNUALLY:
        return 182
    return 365


def get_billing_cycle_months_count(billing_cycle):
    if billing_cycle == Service.MONTHLY:
        return 1
    if billing_cycle == Service.QUARTERLY:
        return 3
    if billing_cycle == Service.BI_ANNUALLY:
        return 6
    return 12


def get_product_model():
    config_model_name = getattr(settings, 'BILLING_PRODUCT_MODEL', 'billing.Product')
    app_label = config_model_name.split('.')[0]
    model = config_model_name.split('.')[1]
    return get_model(app_label, model)


def get_subscription_model():
    config_model_name = getattr(settings, 'BILLING_SUBSCRIPTION_MODEL', 'billing.Subscription')
    app_label = config_model_name.split('.')[0]
    model = config_model_name.split('.')[1]
    return get_model(app_label, model)


def get_next_invoice_number(auto=True):
    """
    Generates the number to use for the next invoice. Auto-generated numbers
    start with "A" whereas manually generated invoice (those generated from the admin panel)
    start with  "M". This is to avoid collision whenever an Invoice is manually generated
    when cron task is running.

    So said if there are currently 999 invoices in the database and the Invoice is
    generated by the cron job, the generated number will be "A1000". If generated
    from the admin, it should be "M1000"

    @param auto: boolean telling whether it was generated by a cron or not
    @return: number identifying the Invoice
    """
    d = strftime(datetime.now(), '%m%y')
    number = Invoice.objects.all().count() + 1
    return "A%d/%s" % (number, d) if auto else "M%d/%s" % (number, d)


def get_subscription_registered_message(subscription):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member upon registration of a Subscription in the database
    @param subscription: Subscription object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = subscription.member
    new_invoice_subject = invoicing_config.new_invoice_subject
    new_invoice_message = invoicing_config.new_invoice_message
    subject = new_invoice_subject if new_invoice_subject else _("Subscription activated")
    if new_invoice_message:
        message = new_invoice_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$amount', config.currency_symbol + ' ' + subscription.monthly_cost)\
            .replace('$details', subscription.product.get_details())\
            .replace('$short_description', subscription.product.short_description)
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "Your subscription to <strong>%(product_name)s</strong> (%(short_description)s) is confirmed. "
                    "See details below:<br><br>"
                    "<span style='color: #444'>%(details)s</span><br>"
                    "Monthly cost: <strong>%(currency)s</strong> %(amount).2f<br>"
                    "Billing cycle: %(billing_cyle)s<br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'product_name': subscription.product.name,
                                           'short_description': subscription.product.short_description,
                                           'amount': subscription.monthly_cost,
                                           'billing_cyle': subscription.billing_cycle,
                                           'currency': config.currency_symbol,
                                           'details': subscription.product.get_details(),
                                           'company_name': config.company_name})
    sms = None
    # if invoicing_config.new_invoice_sms:
    #     sms = invoicing_config.new_invoice_sms.replace('$member_name', member.first_name)\
    #         .replace('$company_name', config.company_name)\
    #         .replace('$invoice_number', subscription.number)\
    #         .replace('$amount', subscription.amount + ' ' + config.currency_symbol)\
    #         .replace('$date_issued', subscription.date_issued)\
    #         .replace('$due_date', subscription.due_date)\
    #         .replace('$invoice_description', subscription.subscription.details)
    return subject, message, sms


def get_invoice_generated_message(invoice):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member upon generation of an invoice
    @param invoice: Invoice object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = invoice.subscription.member
    new_invoice_subject = invoicing_config.new_invoice_subject
    new_invoice_message = invoicing_config.new_invoice_message
    subject = new_invoice_subject if new_invoice_subject else _("Customer Invoice")
    if new_invoice_message:
        message = new_invoice_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.details)
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "This is a notice that an invoice has been generated on %(date_issued)s.<br><br>"
                    "<strong style='font-size: 1.2em'>Invoice #%(invoice_number)s</strong><br>"
                    "Amount: %(currency)s %(amount).2f<br>"
                    "Due Date:  %(due_date)s<br><br>"
                    "<strong>Invoice items:</strong><br>"
                    "<span style='color: #444'>%(invoice_description)s</span><br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'company_name': config.company_name,
                                           'invoice_number': invoice.number,
                                           'amount': invoice.amount,
                                           'currency': config.currency_symbol,
                                           'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                                           'due_date': invoice.due_date.strftime('%B %d, %Y'),
                                           'invoice_description': invoice.subscription.product.get_details()})
    sms = None
    if invoicing_config.new_invoice_sms:
        sms = invoicing_config.new_invoice_sms.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    return subject, message, sms


def get_invoice_reminder_message(invoice):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member as reminder of Invoice payment.
    @param invoice: Invoice object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = invoice.subscription.member
    reminder_subject = invoicing_config.reminder_subject
    reminder_message = invoicing_config.reminder_message
    subject = reminder_subject if reminder_subject else _("Invoice Payment Reminder")
    if reminder_message:
        message = reminder_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "This is a billing reminder that your invoice No. %(invoice_number)s "
                    "which was generated on %(date_issued)s is due on %(due_date)s.<br><br>"
                    "<strong style='font-size: 1.2em'>Invoice #%(invoice_number)s</strong><br>"
                    "Amount: %(currency)s %(amount).2f<br>"
                    "Due Date:  %(due_date)s<br><br>"
                    "<strong>Invoice items:</strong><br>"
                    "<span style='color: #444'>%(invoice_description)s</span><br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'company_name': config.company_name,
                                           'invoice_number': invoice.number,
                                           'amount': invoice.amount,
                                           'currency': config.currency_symbol,
                                           'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                                           'due_date': invoice.due_date.strftime('%B %d, %Y'),
                                           'invoice_description': invoice.subscription.product.get_details()})
    sms = None
    if invoicing_config.reminder_sms:
        sms = invoicing_config.reminder_sms.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    return subject, message, sms


def get_invoice_overdue_message(invoice):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member as reminder of Invoice overdue.
    @param invoice: Invoice object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = invoice.subscription.member
    overdue_subject = invoicing_config.overdue_subject
    overdue_message = invoicing_config.overdue_message

    subject = _("First %s" % overdue_subject) if overdue_subject else _('First notice of Invoice Overdue')
    if invoice.overdue_notices_sent == 1:
        subject = _("Second %s" % overdue_subject) if overdue_subject else _('Second notice of Invoice Overdue')
    elif invoice.overdue_notices_sent == 2:
        subject = _("Third and last %s" % overdue_subject) if overdue_subject else _('Third and last notice of Invoice Overdue')

    if overdue_message:
        message = overdue_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "This is a billing reminder that your invoice No. %(invoice_number)s "
                    "which was due on %(due_date)s is now overdue."
                    "Please pay to avoid service suspension.<br><br>"
                    "<strong style='font-size: 1.2em'>Invoice #%(invoice_number)s</strong><br>"
                    "Amount: %(currency)s %(amount).2f<br>"
                    "Due Date:  %(due_date)s<br><br>"
                    "<strong>Invoice items:</strong><br>"
                    "<span style='color: #444'>%(invoice_description)s</span><br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'company_name': config.company_name,
                                           'invoice_number': invoice.number,
                                           'amount': invoice.amount,
                                           'currency': config.currency_symbol,
                                           'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                                           'due_date': invoice.due_date.strftime('%B %d, %Y'),
                                           'invoice_description': invoice.subscription.product.get_details()})
    sms = None
    if invoicing_config.overdue_sms:
        sms = invoicing_config.overdue_sms.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    return subject, message, sms


def get_service_suspension_message(invoice):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member as notice of Service suspension.
    @param invoice: Invoice object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = invoice.subscription.member
    service_suspension_subject = invoicing_config.payment_confirmation_subject
    service_suspension_message = invoicing_config.payment_confirmation_message
    subject = service_suspension_subject if service_suspension_subject else _("Notice of Service Suspension")
    if service_suspension_message:
        message = service_suspension_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "This a notice of <strong>service suspension</strong> because of unpaid Invoice "
                    "<strong>No. %(invoice_number)s</strong> generated on %(date_issued)s and due on %(due_date)s. <br>"
                    "Amount due is %(currency)s %(amount).2f.<br><br>"
                    "<strong>Invoice items:</strong><br>"
                    "<span style='color: #444'>%(invoice_description)s</span><br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'invoice_number': invoice.number,
                                           'amount': invoice.amount,
                                           'currency': config.currency_symbol,
                                           'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                                           'due_date': invoice.due_date.strftime('%B %d, %Y'),
                                           'invoice_description': invoice.subscription.product.get_details(),
                                           'company_name': config.company_name})
    sms = None
    if invoicing_config.service_suspension_sms:
        sms = invoicing_config.service_suspension_sms.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', invoice.number)\
            .replace('$amount', invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', invoice.date_issued)\
            .replace('$due_date', invoice.due_date)\
            .replace('$invoice_description', invoice.subscription.product.get_details())
    return subject, message, sms


def get_payment_confirmation_message(payment):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member as receipt of Invoice payment.
    @param payment: Payment object
    """
    config = get_service_instance().config
    invoicing_config = InvoicingConfig.objects.all()[0]
    member = payment.invoice.subscription.member
    payment_confirmation_subject = invoicing_config.payment_confirmation_subject
    payment_confirmation_message = invoicing_config.payment_confirmation_message
    subject = payment_confirmation_subject if payment_confirmation_subject else _("Invoice Payment Confirmation")
    if payment_confirmation_message:
        message = payment_confirmation_message.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', payment.invoice.number)\
            .replace('$amount', payment.invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', payment.invoice.date_issued)\
            .replace('$due_date', payment.invoice.due_date)\
            .replace('$invoice_description', payment.invoice.subscription.product.details)
    else:
        message = _("Dear %(member_name)s,<br><br>"
                    "Thank you for your subscription to %(company_name)s. "
                    "This is a payment receipt of %(currency)s %(amount).2f"
                    "for Invoice <strong>No. %(invoice_number)s</strong> generated on %(date_issued)s "
                    "towards the services provided by us. Below is a summary of your invoice.<br>"
                    "<span style='color: #444'>%(invoice_description)s</span><br><br>"
                    "Thank you for your business with "
                    "%(company_name)s." % {'member_name': member.first_name,
                                           'company_name': config.company_name,
                                           'invoice_number': payment.invoice.number,
                                           'amount': payment.invoice.amount,
                                           'currency': config.currency_symbol,
                                           'date_issued': payment.invoice.date_issued.strftime('%B %d, %Y'),
                                           'invoice_description': payment.invoice.subscription.product.get_details()})
    sms = None
    if invoicing_config.payment_confirmation_sms:
        sms = invoicing_config.payment_confirmation_sms.replace('$member_name', member.first_name)\
            .replace('$company_name', config.company_name)\
            .replace('$invoice_number', payment.invoice.number)\
            .replace('$amount', payment.invoice.amount + ' ' + config.currency_symbol)\
            .replace('$date_issued', payment.invoice.date_issued)\
            .replace('$due_date', payment.invoice.due_date)\
            .replace('$invoice_description', payment.invoice.subscription.product.get_details())
    return subject, message, sms


def suspend_subscription(subscription):
    subscription.status = AbstractSubscription.SUSPENDED
    subscription.save()


def check_service_retailer(service):
    """
    This function checks whether the ikwen Service passed as
    parameter is retailed by a partner. If so, the Invoice must
    be generated from the partner billing platform. This function
    will then return True to prevent the main ikwen billing crons
    to issue the invoice to that customer.

    :param service: ikwen Service
    :return: True if the Service is retailed by ikwen. None otherwise
             It is important that this function returns None rather
             than None because the BILLING_BEFORE_NEW_INVOICE will pass
             over if event the returned value is None
    """
    if service.retailer:
        return True
