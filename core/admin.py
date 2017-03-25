# -*- coding: utf-8 -*-
import os

from django.conf import settings
from django.http.response import HttpResponseForbidden
from djangotoolbox.admin import admin
from ikwen.core.utils import generate_favicons

from ikwen.core.models import RETAIL_APP_SLUG

from ikwen.core.models import Application, Config, Service, ConsoleEventType
from django.utils.translation import gettext_lazy as _

__author__ = 'Kom Sihon'


class CustomBaseAdmin(admin.ModelAdmin):

    class Media:
        if not getattr(settings, 'IS_IKWEN', False):
            css = {
                "all": ("ikwen/admin/css/base.css", "ikwen/admin/css/changelists.css", "ikwen/admin/css/dashboard.css",
                        "ikwen/admin/css/forms.css", "ikwen/admin/css/ie.css", "ikwen/admin/css/login.css",
                        "ikwen/admin/css/widget.css", "ikwen/font-awesome/css/font-awesome.min.css",
                        "ikwen/css/flatly.bootstrap.min.css", "ikwen/css/grids.css",
                        "ikwen/billing/admin/css/custom.css",)
            }
        js = ("ikwen/js/jquery-1.12.4.min.js", "ikwen/js/jquery.autocomplete.min.js",
              "ikwen/billing/admin/js/custom.js",)


class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'logo', 'url', 'created_on', 'operators_count', )
    search_fields = ('name', )
    ordering = ('-id', '-operators_count', )
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ('total_turnover', 'total_earnings', 'total_deployment_earnings', 'total_transaction_earnings',
                       'total_invoice_earnings', 'total_custom_service_earnings', 'total_deployment_count', 'total_transaction_count',
                       'total_invoice_count', 'total_custom_service_count', 'total_cash_out', 'total_cash_out_count')
    save_on_top = True

    def save_model(self, request, obj, form, change):
        super(ApplicationAdmin, self).save_model(request, obj, form, change)
        try:
            if os.path.exists(obj.logo.path):
                output_folder = 'ikwen/favicons/%s/' % obj.slug
                if not os.path.exists(getattr(settings, 'MEDIA_ROOT') + output_folder):
                    os.makedirs(getattr(settings, 'MEDIA_ROOT') + output_folder)
                generate_favicons(obj.logo.path, output_folder)
        except ValueError:
            pass


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('project_name', 'app', 'member', 'monthly_cost', 'expiry', 'since', 'version', 'status', )
    raw_id_fields = ('member', )
    search_fields = ('project_name', )
    list_filter = ('app', 'version', 'expiry', 'since', 'status', )
    ordering = ('-id', )
    readonly_fields = ('retailer', 'since',
                       'total_turnover', 'total_earnings', 'total_transaction_earnings', 'total_custom_service_earnings',
                       'total_invoice_earnings', 'total_transaction_count', 'total_cash_out',
                       'total_invoice_count', 'total_custom_service_count', 'total_cash_out_count')

    def save_model(self, request, obj, form, change):
        if obj.app.slug == RETAIL_APP_SLUG and not change:
            from ikwen.partnership.cloud_setup import deploy
            member = request.user
            project_name = request.POST['project_name']
            monthly_cost = request.POST['monthly_cost']
            billing_cycle = request.POST['billing_cycle']
            domain = request.POST['domain']
            is_pro_version = True if request.POST.get('is_pro_version') else False
            deploy(obj.app, member, project_name, monthly_cost, billing_cycle, domain, is_pro_version)
        else:
            super(ServiceAdmin, self).save_model(request, obj, form, change)


class ConfigAdmin(admin.ModelAdmin):
    list_display = ('service', 'company_name', 'short_description', 'contact_email', 'contact_phone')
    fieldsets = (
        (_('General'), {'fields': ('service', 'company_name', 'short_description', 'slogan',
                                   'description', 'currency_code', 'currency_symbol',)}),
        (_('Address & Contact'), {'fields': ('contact_email', 'contact_phone', 'address', 'country', 'city')}),
        (_('Social'), {'fields': ('facebook_link', 'twitter_link', 'google_plus_link', 'instagram_link', 'linkedin_link', )}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature', )}),
    )
    list_filter = ('company_name', 'contact_email', )
    save_on_top = True

    def delete_model(self, request, obj):
        if Config.objects.all().count() == 1:
            return HttpResponseForbidden("You are not allowed to delete Configuration of the platform")
        super(ConfigAdmin, self).delete_model(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return ('service',)
        return ()


class ConsoleEventTypeAdmin(admin.ModelAdmin):
    list_display = ('app', 'codename', 'title', 'renderer', 'min_height',)
    search_fields = ('codename', 'title',)
    list_filter = ('app',)


if getattr(settings, 'IS_UMBRELLA', False):
    admin.site.register(Application, ApplicationAdmin)
    admin.site.register(Config, ConfigAdmin)
    admin.site.register(Service, ServiceAdmin)
    admin.site.register(ConsoleEventType, ConsoleEventTypeAdmin)
# admin.site.register(Country, CountryAdmin)