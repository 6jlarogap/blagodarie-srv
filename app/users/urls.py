from django.conf.urls import url
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    url(r'^api/auth/signup/?$', views.api_auth_signup),
    url(r'^api/auth/signin/?$', views.api_auth_signup,  {'signin': True}),

    url(r'^api/auth/signup/incognito/?$', views.api_auth_signup_incognito),

    url(r'^api/getprofileinfo/?$', views.api_get_profileinfo),
    url(r'^api/updateprofileinfo/?$', views.api_update_profileinfo),

    url(r'^api/auth/dummy/?$', views.api_auth_dummy),

    url(r'^api/download\-apk\-details/?$', views.api_download_apk_details),
    url(r'^api/getlatestversion/?$', views.api_latest_version),

    url(r'^api/download\-rating\-apk\-details/?$', views.api_download_rating_apk_details),
    url(r'^api/getratinglatestversion/?$', views.api_rating_latest_version),

    url(r'^api/getusers/?$', views.api_get_users),

    url(r'^api/auth/telegram/?$', views.api_auth_telegram),

    url(r'^api/oauth/callback/(?P<provider>yandex|vk|odnoklassniki)/?$', views.api_oauth_callback),

    url(r'^api/update\-frontend\-site/?$', views.api_update_frontend_site),
]
