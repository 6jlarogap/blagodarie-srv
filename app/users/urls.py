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

    re_path(r'^api/user/relations/?$', views.api_user_relations),
    re_path(r'^api/user/points/?$', views.api_user_points),

    re_path(r'^api/bot/stat/?$', views.api_bot_stat),
    re_path(r'^api/bot/group/?$', views.api_bot_group),
    re_path(r'^api/bot/groupmember/?$', views.api_bot_groupmember),

    re_path(r'^api/bot/poll/?$', views.api_bot_poll),
    re_path(r'^api/bot/poll/answer/?$', views.api_bot_poll_answer),
    re_path(r'^api/bot/poll/results/?$', views.api_bot_poll_results),

    re_path(r'^api/offer/?$', views.api_offer),
    re_path(r'^api/offer/answer/?$', views.api_offer_answer),
    re_path(r'^api/offer/results/?$', views.api_offer_results),
    re_path(r'^api/offer/voted/tg_users?$', views.api_offer_voted_tg_users),

    re_path(r'^api/token/url/?$', views.api_token_url),

    re_path(r'^test/goto/(?P<temp_token>[a-f0-9]{40})/link/?$', views.test_goto_auth_link),

]
