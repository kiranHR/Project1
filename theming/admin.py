from django.conf import settings
from django.contrib import admin
from ikwen.theming.models import Template, Theme, ThemePreview


class TemplateAdmin(admin.ModelAdmin):
    list_display = ('app', 'name', 'preview', )
    search_fields = ('name',)
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ('app',)


class ThemePreviewInline(admin.TabularInline):
    model = ThemePreview
    fields = ('image', )


class ThemeAdmin(admin.ModelAdmin):
    if getattr(settings, 'IS_IKWEN', False):
        list_display = ('template', 'name', 'preview',)
        search_fields = ('name',)
        prepopulated_fields = {"slug": ("name",)}
        list_filter = ('template',)
        inlines = (ThemePreviewInline, )
    else:
        fields = ('name', 'display', )
        readonly_fields = ('name', )


if getattr(settings, 'IS_UMBRELLA', False):
    admin.site.register(Template, TemplateAdmin)
    admin.site.register(Theme, ThemeAdmin)
