#
# youtube_upload.py
#
# Credits to:
#   https://medium.com/@nijmehar16/uploading-videos-to-youtube-via-the-youtube-api-programmatically-which-uses-oauth-2-0-7317ec72411e

import http.client as httplib
import httplib2
import os
import random
import sys
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow
from oauth2client import GOOGLE_REVOKE_URI, GOOGLE_TOKEN_URI, client

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, httplib.NotConnected,
                        httplib.IncompleteRead, httplib.ImproperConnectionState,
                        httplib.CannotSendRequest, httplib.CannotSendHeader,
                        httplib.ResponseNotReady, httplib.BadStatusLine)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google API Console at
# https://console.cloud.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets.json"

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.cloud.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

def get_authenticated_service(auth_data):

    credentials = client.OAuth2Credentials(
        access_token=None,
        client_id=auth_data['client_id'],
        client_secret=auth_data['client_secret'],
        refresh_token=auth_data['refresh_token'],
        token_expiry=None,
        token_uri=GOOGLE_TOKEN_URI,
        user_agent=None,
        revoke_uri=None)
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))

def initialize_upload(youtube, fname, body):
    # Call the API's videos.insert method to create and upload the video.
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        # The chunksize parameter specifies the size of each chunk of data, in
        # bytes, that will be uploaded at a time. Set a higher value for
        # reliable connections as fewer chunks lead to faster uploads. Set a lower
        # value for better recovery on less reliable connections.
        #
        # Setting "chunksize" equal to -1 in the code below means that the entire
        # file will be uploaded in a single HTTP request. (If the upload fails,
        # it will still be retried where it left off.) This is usually a best
        # practice, but if you're using Python older than 2.6 or if you're
        # running on App Engine, you should set the chunksize to something like
        # 1024 * 1024 (1 megabyte).
        media_body=MediaFileUpload(fname, chunksize=-1, resumable=True)
    )
    return resumable_upload(insert_request)


# This method implements an exponential backoff strategy to resume a
# failed upload.
def resumable_upload(insert_request):
    response = None
    error = None
    retry = 0
    msg_unknown = 'Неизвестная ошибка'
    while response is None:
        retriable = False
        try:
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' not in response:
                    error = msg_unknown
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = e.reason if e.reason else msg_unknown
                error = f'Статус {e.resp.status}:\n{error}'
                retriable = True
            else:
                error = e.reason if e.reason else msg_unknown
        except RETRIABLE_EXCEPTIONS as e:
            error = e
            retriable = True
        except:
            error = e

        if retriable:
            if error is not None:
                retry += 1
                if retry > MAX_RETRIES:
                    return response, error

                max_sleep = 2 ** retry
                sleep_seconds = random.random() * max_sleep
                time.sleep(sleep_seconds)
        else:
            break
    return response, error

def upload_video(
    # video fname to upload
    #
    fname,

    # dict(
    #     client_id='client_id',
    #     client_secret='client_secret',
    #     refresh_token='refresh_token'
    # )
    #
    auth_data,

    # https://developers.google.com/youtube/v3/docs/videos/insert
    #
    snippet={},
    status={},
):
    if not snippet.get('title'):
        snippet['title'] ='Test Title'
    if not snippet.get('description'):
        snippet['description'] ='Test Description'
    if not snippet.get('category'):
        snippet['category'] = '22'
    if not snippet.get('tags'):
        snippet['tags'] = []

    if not status.get('privacyStatus'):
        status['privacyStatus'] = VALID_PRIVACY_STATUSES[0]

    if 'selfDeclaredMadeForKids' not in status:
        # Иначе, чем False здесь, YouTube не примет!
        #
        status['selfDeclaredMadeForKids'] = False

    youtube = get_authenticated_service(auth_data)
    return initialize_upload(youtube, fname, dict(snippet=snippet, status=status))
