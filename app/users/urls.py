from django.conf.urls import url
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    url(r'^api/auth/signup?$', views.api_auth_signup),
    url(r'^api/auth/signin?$', views.api_auth_signup,  {'signin': True}),
    url(r'^api/auth/dummy?$', views.api_auth_dummy),
]
