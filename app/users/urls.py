from django.urls import re_path
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    re_path(r'^api/auth/signup/incognito/?$', views.api_auth_signup_incognito),

    re_path(r'^api/getprofileinfo/?$', views.api_get_profileinfo),

    re_path(r'^api/download\-apk\-details/?$', views.api_download_apk_details),
    re_path(r'^api/getlatestversion/?$', views.api_latest_version),

    re_path(r'^api/download\-rating\-apk\-details/?$', views.api_download_rating_apk_details),
    re_path(r'^api/getratinglatestversion/?$', views.api_rating_latest_version),

    re_path(r'^api/auth/telegram/?$', views.api_auth_telegram),

    re_path(r'^api/oauth/callback/(?P<provider>yandex|vk|odnoklassniki)/?$', views.api_oauth_callback),

    re_path(r'^api/update\-frontend\-site/?$', views.api_update_frontend_site),

    re_path(r'^api/invite/gettoken/?$', views.api_invite_get_token),

    re_path(r'^api/profile/?$', views.api_profile),
]
