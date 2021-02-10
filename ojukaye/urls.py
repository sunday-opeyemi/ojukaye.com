"""ojukaye URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path
from django.conf.urls import include, url
from django.views.generic import TemplateView
from ojukaye.newsapp import views as newsapp_views
from ojukaye.adminapp import views as admin_views
from ojukaye.userportalapp import views as userportal_views
from django.contrib.auth import views
from . import settings
from django.contrib.staticfiles.urls import static, staticfiles_urlpatterns
from .newsapp.views import SignUpView

urlpatterns = [
    path('admin/', admin.site.urls),
    url(r'^$', newsapp_views.homepage, name='index'),
    url(r'^services', TemplateView.as_view(template_name='services.html'), name="services"),
    url(r'^product', TemplateView.as_view(template_name='product.html'), name='products'),
    url(r'^contact', TemplateView.as_view(template_name='contact.html'), name='contact'),
    url(r'^helpcenter', TemplateView.as_view(template_name='helpcenter.html'), name='helpcenter'),
    url(r'^adminapp/', include('ojukaye.adminapp.urls')),
    url(r'^newsapp/', include('ojukaye.newsapp.urls')),
    url(r'^userportalapp/', include('ojukaye.userportalapp.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^accounts/signup/$', SignUpView.as_view(), name="signup"),
    url(r'^(?P<username>.+)/$', userportal_views.user_portal, name=r'^(?P<username>.+)/$'),
]

urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)