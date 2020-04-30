from django.conf.urls import url
from django.views.generic.base import RedirectView

from django.conf import settings

from . import views

urlpatterns = [
    url(r'^api/adduser/?$', views.api_add_user),
    url(r'^api/getorcreateuser/?$', views.api_get_or_create_user),

    url(r'^api/deleteuserkeyz/?$', views.api_delete_user_keys),
 
    url(r'^api/addkeyz/?$', views.api_add_key),
    url(r'^api/getorcreatekeyz/?$', views.get_or_create_key),

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
    url(r'^api/getstats/symptoms?$', views.api_get_stats, {'only': 'symptoms'}),
    url(r'^api/getstats/symptoms/hist?$', views.api_get_stats, {'only': 'symptoms_hist'}),

    url(r'^api/getlatestversion/?$', views.api_latest_version_old),
    url(r'^api/getlatestversion_new/?$', views.api_latest_version_new),

    url(r'^api/addusersymptom/?$', views.api_add_user_symptom),
    url(r'^api/add_user_symptom/?$', views.api_add_user_symptom_new),

]
