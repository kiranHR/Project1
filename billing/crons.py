#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen.conf.settings")

from datetime import datetime, timedelta
from django.conf import settings
from django.db.models import Q
from django.contrib.auth.models import Group
from django.core import mail
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.module_loading import import_by_path
from ikwen.accesscontrol.models import SUDO

from ikwen.core.models import Config, QueuedSMS
from ikwen.core.utils import get_service_instance, send_sms, add_event
from ikwen.core.utils import get_mail_content
from ikwen.billing.models import Invoice, InvoicingConfig, INVOICES_SENT_EVENT, \
    NEW_INVOICE_EVENT, INVOICE_REMINDER_EVENT, REMINDERS_SENT_EVENT, OVERDUE_NOTICE_EVENT, OVERDUE_NOTICES_SENT_EVENT, \
    SUSPENSION_NOTICES_SENT_EVENT, SERVICE_SUSPENDED_EVENT, SendingReport
from ikwen.billing.utils import get_invoice_generated_message, get_invoice_reminder_message, get_invoice_overdue_message, \
    get_service_suspension_message, get_next_invoice_number, get_subscription_model, get_billing_cycle_months_count

import logging
import logging.handlers
error_log = logging.getLogger('crons.error')
error_log.setLevel(logging.ERROR)
error_file_handler = logging.handlers.RotatingFileHandler('billing_crons.log', 'w', 100000, 4)
error_file_handler.setLevel(logging.INFO)
f = logging.Formatter('%(levelname)-10s %(asctime)-27s %(message)s')
error_file_handler.setFormatter(f)
error_log.addHandler(error_file_handler)

Subscription = get_subscription_model()


def send_invoices():
    """
    This cron task simply sends the Invoice *invoicing_gap* days before Subscription *expiry*
    """
    service = get_service_instance()
    config = service.config
    now = datetime.now()
    invoicing_config = InvoicingConfig.objects.all()[0]
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        error_log.error(u"Connexion error", exc_info=True)
    count, total_amount = 0, 0
    reminder_date_time = now + timedelta(days=invoicing_config.gap)
    for subscription in Subscription.objects.filter(Q(status=Subscription.ACTIVE) | Q(status=Subscription.PENDING),
                                                    monthly_cost__gt=0, expiry=reminder_date_time.date()):
        member = subscription.member
        number = get_next_invoice_number()
        months_count = None
        if config.__dict__.get('separate_billing_cycle', True):
            months_count = get_billing_cycle_months_count(subscription.billing_cycle)
            amount = subscription.monthly_cost * months_count
        else:
            amount = subscription.product.cost

        path_before = getattr(settings, 'BILLING_BEFORE_NEW_INVOICE', None)
        if path_before:
            before_new_invoice = import_by_path(path_before)
            val = before_new_invoice(subscription)
            if val is not None:  # Returning a not None value cancels the generation of a new Invoice for this Service
                continue

        invoice = Invoice.objects.create(subscription=subscription, amount=amount,
                                         number=number, due_date=subscription.expiry, months_count=months_count)
        count += 1
        total_amount += amount
        add_event(service, NEW_INVOICE_EVENT, member=member, object_id=invoice.id)
        subject, message, sms_text = get_invoice_generated_message(invoice)
        if member.email and member.email.find(member.phone) < 0:
            invoice_url = service.url + reverse('billing:invoice_detail', args=(invoice.id,))
            html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                            extra_context={'invoice_url': invoice_url})
            # Sender is simulated as being no-reply@company_name_slug.com to avoid the mail
            # to be delivered to Spams because of origin check.
            sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
            msg = EmailMessage(subject, html_content, sender, [member.email])
            msg.content_subtype = "html"
            invoice.last_reminder = timezone.now()
            try:
                if msg.send():
                    invoice.reminders_sent = 1
                else:
                    error_log.error(u"Invoice #%s generated but mail not sent to %s" % (number, member.email),
                                    exc_info=True)
            except:
                error_log.error(u"Connexion error on Invoice #%s to %s" % (number, member.email), exc_info=True)
            invoice.save()
        if sms_text:
            if member.phone:
                if config.sms_sending_method == Config.HTTP_API:
                    send_sms(member.phone, sms_text)
                else:
                    QueuedSMS.objects.create(recipient=member.phone, text=sms_text)

        path_after = getattr(settings, 'BILLING_AFTER_NEW_INVOICE', None)
        if path_after:
            after_new_invoice = import_by_path(path_after)
            after_new_invoice(invoice)

    try:
        connection.close()
    finally:
        if count > 0:
            report = SendingReport.objects.create(count=count, total_amount=total_amount)
            sudo_group = Group.objects.get(name=SUDO)
            add_event(service, INVOICES_SENT_EVENT, group_id=sudo_group.id, object_id=report.id)


def send_invoice_reminders():
    """
    This cron task sends Invoice reminder notice to the client if unpaid
    """
    service = get_service_instance()
    config = service.config
    now = datetime.now()
    invoicing_config = InvoicingConfig.objects.all()[0]
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        error_log.error(u"Connexion error", exc_info=True)
    count, total_amount = 0, 0
    for invoice in Invoice.objects.filter(status=Invoice.PENDING, due_date__gte=now.date(),
                                          last_reminder__isnull=False):
        diff = now - invoice.last_reminder
        if diff.days == invoicing_config.reminder_delay:
            count += 1
            total_amount += invoice.amount
            member = invoice.subscription.member
            add_event(service, INVOICE_REMINDER_EVENT, member=member, object_id=invoice.id)
            subject, message, sms_text = get_invoice_reminder_message(invoice)
            if member.email and member.email.find(member.phone) < 0:
                invoice_url = service.url + reverse('billing:invoice_detail', args=(invoice.id,))
                html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                                extra_context={'invoice_url': invoice_url})
                # Sender is simulated as being no-reply@company_name_slug.com to avoid the mail
                # to be delivered to Spams because of origin check.
                sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
                msg = EmailMessage(subject, html_content, sender, [member.email])
                msg.content_subtype = "html"
                invoice.last_reminder = timezone.now()
                try:
                    if msg.send():
                        invoice.reminders_sent += 1
                    else:
                        error_log.error(u"Reminder mail for Invoice #%s not sent to %s" % (invoice.number, member.email), exc_info=True)
                except:
                    error_log.error(u"Connexion error on Invoice #%s to %s" % (invoice.number, member.email), exc_info=True)
                invoice.save()
            if sms_text:
                if member.phone:
                    if config.sms_sending_method == Config.HTTP_API:
                        send_sms(member.phone, sms_text)
                    else:
                        QueuedSMS.objects.create(recipient=member.phone, text=sms_text)
    try:
        connection.close()
    finally:
        if count > 0:
            report = SendingReport.objects.create(count=count, total_amount=total_amount)
            sudo_group = Group.objects.get(name=SUDO)
            add_event(service, REMINDERS_SENT_EVENT, group_id=sudo_group.id, object_id=report.id)


def send_invoice_overdue_notices():
    """
    This cron task sends notice of Invoice overdue
    """
    service = get_service_instance()
    config = service.config
    now = timezone.now()
    invoicing_config = InvoicingConfig.objects.all()[0]
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        error_log.error(u"Connexion error", exc_info=True)
    count, total_amount = 0, 0
    for invoice in Invoice.objects.filter(status=Invoice.PENDING, due_date__lt=now, overdue_notices_sent__lt=3):
        if invoice.last_overdue_notice:
            diff = now - invoice.last_overdue_notice
        else:
            invoice.status = Invoice.OVERDUE
            invoice.save()
        if not invoice.last_overdue_notice or diff.days == invoicing_config.overdue_delay:
            count += 1
            total_amount += invoice.amount
            member = invoice.subscription.member
            add_event(service, OVERDUE_NOTICE_EVENT, member=member, object_id=invoice.id)
            subject, message, sms_text = get_invoice_overdue_message(invoice)
            if member.email and member.email.find(member.phone) < 0:
                invoice_url = service.url + reverse('billing:invoice_detail', args=(invoice.id,))
                html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                                extra_context={'invoice_url': invoice_url})
                # Sender is simulated as being no-reply@company_name_slug.com to avoid the mail
                # to be delivered to Spams because of origin check.
                sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
                msg = EmailMessage(subject, html_content, sender, [member.email])
                msg.content_subtype = "html"
                invoice.last_overdue_notice = timezone.now()
                try:
                    if msg.send():
                        invoice.overdue_notices_sent += 1
                    else:
                        error_log.error(u"Overdue notice for Invoice #%s not sent to %s" % (invoice.number, member.email), exc_info=True)
                except:
                    error_log.error(u"Connexion error on Invoice #%s to %s" % (invoice.number, member.email), exc_info=True)
                invoice.save()
            if sms_text:
                if member.phone:
                    if config.sms_sending_method == Config.HTTP_API:
                        send_sms(member.phone, sms_text)
                    else:
                        QueuedSMS.objects.create(recipient=member.phone, text=sms_text)
    try:
        connection.close()
    finally:
        if count > 0:
            report = SendingReport.objects.create(count=count, total_amount=total_amount)
            sudo_group = Group.objects.get(name=SUDO)
            add_event(service, OVERDUE_NOTICES_SENT_EVENT, group_id=sudo_group.id, object_id=report.id)


def suspend_customers_services():
    """
    This cron task shuts down service and sends notice of Service suspension
    for Invoices which tolerance is exceeded.
    """
    service = get_service_instance()
    config = service.config
    now = timezone.now()
    invoicing_config = InvoicingConfig.objects.all()[0]
    connection = mail.get_connection()
    try:
        connection.open()
    except:
        error_log.error(u"Connexion error", exc_info=True)
    count, total_amount = 0, 0
    deadline = now - timedelta(days=invoicing_config.tolerance)
    for invoice in Invoice.objects.filter(due_date__lte=deadline, status=Invoice.PENDING):
        invoice.status = Invoice.EXCEEDED
        invoice.save()
        action = getattr(settings, 'SERVICE_SUSPENSION_ACTION', None)
        if action:
            count += 1
            total_amount += invoice.amount
            action = import_by_path(action)
            action(invoice.subscription)
            member = invoice.subscription.member
            add_event(service, SERVICE_SUSPENDED_EVENT, member=member, object_id=invoice.id)
            subject, message, sms_text = get_service_suspension_message(invoice)
            if member.email and member.email.find(member.phone) < 0:
                invoice_url = service.url + reverse('billing:invoice_detail', args=(invoice.id,))
                html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                                extra_context={'invoice_url': invoice_url})
                # Sender is simulated as being no-reply@company_name_slug.com to avoid the mail
                # to be delivered to Spams because of origin check.
                sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
                msg = EmailMessage(subject, html_content, sender, [member.email])
                msg.content_subtype = "html"
                try:
                    if not msg.send():
                        error_log.error(u"Notice of suspension for Invoice #%s not sent to %s" % (invoice.number, member.email), exc_info=True)
                except:
                    error_log.error(u"Connexion error on Invoice #%s to %s" % (invoice.number, member.email), exc_info=True)
            if sms_text:
                if member.phone:
                    if config.sms_sending_method == Config.HTTP_API:
                        send_sms(member.phone, sms_text)
                    else:
                        QueuedSMS.objects.create(recipient=member.phone, text=sms_text)
    try:
        connection.close()
    finally:
        if count > 0:
            report = SendingReport.objects.create(count=count, total_amount=total_amount)
            sudo_group = Group.objects.get(name=SUDO)
            add_event(service, SUSPENSION_NOTICES_SENT_EVENT, group_id=sudo_group.id, object_id=report.id)


if __name__ == "__main__":
    try:
        send_invoices()
        send_invoice_reminders()
        send_invoice_overdue_notices()
        suspend_customers_services()
    except:
        error_log.error(u"Fatal error occured", exc_info=True)