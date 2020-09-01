from django.conf.urls import url
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    url(r'^api/addoperation/?$', views.api_add_operation),
    url(r'^api/getuseroperations/?$', views.api_get_user_operations),

    url(r'^api/addtextoperation/?$', views.api_add_text_operation),
    url(r'^api/gettextinfo/?$', views.api_get_textinfo),
    url(r'^api/gettextoperations/?$', views.api_get_text_operations),

    url(r'^api/deleteuserkeyz/?$', views.api_delete_user_keys),
 
    url(r'^api/addkeyz/?$', views.api_add_keyz),
    url(r'^api/getorcreatekeyz/?$', views.get_or_create_key),
    url(r'^api/getuserkeys/?$', views.api_get_user_keys),
    url(r'^api/addkey/?$', views.api_add_key),
    url(r'^api/updatekey/?$', views.api_update_key),
    url(r'^api/deletekey/?$', views.api_delete_key),

    url(r'^api/getlikes/?$', views.api_get_likes),
    url(r'^api/getlikesbykeyz/?$', views.api_get_all_likes, {'by': 'keys'}),
    url(r'^api/getlikesbykeyzid/?$', views.api_get_all_likes, {'by': 'ids'}),

    url(r'^api/addlikes/?$', views.api_add_like),
    url(r'^api/cancellikes/?$', views.api_cancel_likes),
    url(r'^api/deletelikes/?$', views.api_delete_likes),

    url(r'^api/deletelikekeyz/?$', views.api_delete_like_keys),

    url(r'^api/getorcreatelikekeyz/?$', views.get_or_create_like_key),

    url(r'^api/getcontactsuminfo/?$', views.api_get_contacts_sum_info, {'by': 'values'}),
    url(r'^api/getcontactsuminfobyid/?$', views.api_get_contacts_sum_info, {'by': 'ids'}),

    url(r'^api/getstats/?$', views.api_get_stats),
    url(r'^api/getstats/users/?$', views.api_get_stats, {'only': 'users'}),
    url(r'^api/getstats/symptoms/?$', views.api_get_stats, {'only': 'symptoms'}),
    url(r'^api/getstats/symptoms/hist/?$', views.api_get_stats, {'only': 'symptoms_hist'}),
    url(r'^api/getstats/symptoms/names/?$', views.api_get_stats, {'only': 'symptoms_names'}),

    url(r'^api/getstats/symptoms/hist/data/?$',
        views.api_get_stats, {'only': 'symptoms_hist_data'}),
    url(r'^api/getstats/symptoms/moon/data/?$',
        views.api_get_stats, {'only': 'symptoms_moon_data'}),

    url(r'^api/getstats/user_connections/?$', views.api_get_stats, {'only': 'user_connections'}),
    url(r'^api/getstats/user_connections_graph/?$', views.api_get_stats, {'only': 'user_connections_graph'}),

    url(r'^api/addusersymptom/?$', views.api_add_user_symptom),
    url(r'^api/add_user_symptom/?$', views.api_add_user_symptom, {'auth': True}),
    url(r'^api/addincognitosymptom/?$', views.api_add_user_symptom, {'auth': False}),

    url(r'^api/getsymptoms/?$', views.api_getsymptoms),

    url(r'^api/addorupdatewish/?$', views.api_add_or_update_wish),
    url(r'^api/getwishinfo/?$', views.api_get_wish_info),
    url(r'^api/getuserwishes/?$', views.api_get_user_wishes),
    url(r'^api/deletewish/?$', views.api_delete_wish),

    url(r'^admin/merge_symptoms/?$', views.merge_symptoms),
]
