from django.conf import settings

def global_template_variables(request):
    return {'JQUERY_URL': settings.JQUERY_URL,
             'JQUERYUI_URL': settings.JQUERYUI_URL,
             'JQUERYUI_CSS': settings.JQUERYUI_CSS,
             'ANALYTICS_SNIPPET': settings.ANALYTICS_SNIPPET,
             'VERSION': settings.QUEST['version'],
             'ADMIN_EMAIL': settings.QUEST['ADMIN_EMAIL'],
             'ADMIN_NAME': settings.QUEST['ADMIN_NAME'],
             'SITE_NAME': settings.QUEST['SITE_NAME'],
             'FULL_DOMAIN_NO_HTTP': settings.QUEST['FULL_DOMAIN_NO_HTTP'],
            }