# store_from_photo_url.py

# Загрузить фото из Profile.photo_url, где возможно, в Profile.photo,
# если Profile.photo пуст

# Запуск из ./manage.py shell:
# exec(open('../contrib/store_from_photo_url.py').read())

import urllib.request, urllib.error

from django.conf import settings
from django.db.models.query_utils import Q
from django.core.files.base import ContentFile

from app.models import PhotoModel
from users.models import Profile

from restthumbnails.files import ThumbnailContentFile

q = Q(photo='') | Q(photo__isnull=True)
q &= Q(photo_url__gt='')
for profile in Profile.objects.select_related('user').filter(q):
    photo_url = PhotoModel.tweek_photo_url(profile.photo_url)
    print(profile.user.first_name)
    print('   ', photo_url)

    try:
        req = urllib.request.Request(photo_url)
        r = urllib.request.urlopen(req, timeout=60)
        if r.getcode() != 200:
            print('       ', 'ERROR: status != 200')
            continue
        content = ContentFile(r.read(), 'photo.jpg')
        content = ThumbnailContentFile(
            content,
            quality=settings.PHOTO_QUALITY,
            minsize=settings.PHOTO_QUALITY_MIN_SIZE or 0,
        ).generate()
        if not content:
            print('       ', 'ERROR: not an image')
            continue
        profile.photo.save(PhotoModel.DEFAULT_FNAME, content)
        print('       ', 'success')
    except urllib.error.URLError as url_error:
        print('       ', 'ERROR: connection or alike: %s' % url_error)
        continue
