from django.urls import re_path
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    re_path(r'^api/addoperation/?$', views.api_add_operation),
    re_path(r'^api/getuseroperations/?$', views.api_get_user_operations),

    re_path(r'^api/addtextoperation/?$', views.api_add_text_operation),
    re_path(r'^api/gettextinfo/?$', views.api_get_textinfo),
    re_path(r'^api/gettextoperations/?$', views.api_get_text_operations),

    re_path(r'^api/deleteuserkeyz/?$', views.api_delete_user_keys),
 
    re_path(r'^api/addkeyz/?$', views.api_add_keyz),
    re_path(r'^api/getorcreatekeyz/?$', views.get_or_create_key),
    re_path(r'^api/getuserkeys/?$', views.api_get_user_keys),
    re_path(r'^api/addkey/?$', views.api_add_key),
    re_path(r'^api/updatekey/?$', views.api_update_key),
    re_path(r'^api/deletekey/?$', views.api_delete_key),

    #re_path(r'^api/getlikes/?$', views.api_get_likes),
    #re_path(r'^api/getlikesbykeyz/?$', views.api_get_all_likes, {'by': 'keys'}),
    #re_path(r'^api/getlikesbykeyzid/?$', views.api_get_all_likes, {'by': 'ids'}),

    #re_path(r'^api/addlikes/?$', views.api_add_like),
    #re_path(r'^api/cancellikes/?$', views.api_cancel_likes),
    #re_path(r'^api/deletelikes/?$', views.api_delete_likes),

    #re_path(r'^api/deletelikekeyz/?$', views.api_delete_like_keys),

    #re_path(r'^api/getorcreatelikekeyz/?$', views.get_or_create_like_key),

    re_path(r'^api/getcontactsuminfo/?$', views.api_get_contacts_sum_info, {'by': 'values'}),
    re_path(r'^api/getcontactsuminfobyid/?$', views.api_get_contacts_sum_info, {'by': 'ids'}),

    re_path(r'^api/getstats/?$', views.api_get_stats),
    re_path(r'^api/getstats/users/?$', views.api_get_stats, {'only': 'users'}),
    re_path(r'^api/getstats/symptoms/?$', views.api_get_stats, {'only': 'symptoms'}),
    re_path(r'^api/getstats/symptoms/names/?$', views.api_get_stats, {'only': 'symptoms_names'}),

    re_path(r'^api/getstats/symptoms/hist/data/?$',
        views.api_get_stats, {'only': 'symptoms_hist_data'}),
    re_path(r'^api/getstats/symptoms/moon/data/?$',
        views.api_get_stats, {'only': 'symptoms_moon_data'}),

    re_path(r'^api/getstats/user_connections/?$', views.api_get_stats, {'only': 'user_connections'}),
    re_path(r'^api/getstats/user_connections_graph/?$', views.api_get_stats, {'only': 'user_connections_graph'}),

    re_path(r'^api/profile_graph/?$', views.api_profile_graph),

    re_path(r'^api/addusersymptom/?$', views.api_add_user_symptom),
    re_path(r'^api/add_user_symptom/?$', views.api_add_user_symptom, {'auth': True}),
    re_path(r'^api/addincognitosymptom/?$', views.api_add_user_symptom, {'auth': False}),

    re_path(r'^api/getsymptoms/?$', views.api_getsymptoms),
    re_path(r'^api/getincognitomessages/?$', views.api_getincognitomessages),

    re_path(r'^api/addorupdatewish/?$', views.api_add_or_update_wish),
    re_path(r'^api/getwishinfo/?$', views.api_get_wish_info),
    re_path(r'^api/getuserwishes/?$', views.api_get_user_wishes),
    re_path(r'^api/deletewish/?$', views.api_delete_wish),

    re_path(r'^api/getthanksusers/?$', views.api_get_thanks_users),
    re_path(r'^api/getthanksusersforanytext/?$', views.api_get_thanks_users_for_anytext),

    re_path(r'^api/addorupdateability/?$', views.api_add_or_update_ability),
    re_path(r'^api/getuserabilities/?$', views.api_get_user_abilities),
    re_path(r'^api/deleteability/?$', views.api_delete_ability),

    re_path(r'^api/invite/usetoken/?$', views.api_invite_use_token),

    re_path(r'^admin/merge_symptoms/?$', views.merge_symptoms),
]
