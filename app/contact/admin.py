import time

from django.contrib import admin

from .models import Key, UserKey, Like, LikeKey

class KeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'type_', 'value',)

    def type_(self, obj):
        return '(%s) %s' % (obj.type.pk, obj.type.title,)

class UserKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'key',)

    def user_id(self, obj):
        return obj.user.pk

class LikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner_id', 'insert_timestamp_', 'cancel_timestamp_', 'update_timestamp_')

    def owner_id(self, obj):
        return obj.owner.pk

    def insert_timestamp_(self, obj):
        return '%s (%s)' % (obj.insert_timestamp, time.ctime(obj.insert_timestamp))

    def cancel_timestamp_(self, obj):
        if obj.cancel_timestamp:
            return '%s (%s)' % (obj.cancel_timestamp, time.ctime(obj.cancel_timestamp))
        else:
            return '-'

    def update_timestamp_(self, obj):
        return '%s (%s)' % (obj.update_timestamp, time.ctime(obj.update_timestamp))

class LikeKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'like', 'key', )

admin.site.register(Key, KeyAdmin)
admin.site.register(UserKey, UserKeyAdmin)
admin.site.register(Like, LikeAdmin)
admin.site.register(LikeKey, LikeKeyAdmin)
