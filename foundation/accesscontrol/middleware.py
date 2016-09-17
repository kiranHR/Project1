# -*- coding: utf-8 -*-
from django.contrib.auth import authenticate, login, logout
from django.http.response import HttpResponseRedirect
from django.utils.http import urlsafe_base64_decode

UID_B64 = 'key'
TOKEN = 'rand'
TOKEN_CHUNK = 15


class XDomainTokenAuthMiddleware(object):
    """
    Middleware that authenticates user across domains using those two:
        * uidb64: Base 64 encoded user Id
        * token: characters of the encoded user password in the range [-TOKEN_CHUNK:-1]
    Those two parameters are passed around as GET data. When detected on a URL,
    the middleware will check if they are valid and login the user.
    """
    def process_request(self, request):
        uidb64 = request.GET.get(UID_B64)
        token = request.GET.get(TOKEN)
        if request.user.is_authenticated():
            if uidb64 and token:
                uid = urlsafe_base64_decode(uidb64)
                member = request.user
                if member.id != uid or token != member.password[-TOKEN_CHUNK:-1]:
                    logout(request)
                    tokens_string = UID_B64 + '=' + uidb64 + '&' + TOKEN + '=' + token
                    raw_next_url = request.build_absolute_uri().replace(tokens_string, '').strip('?').strip('&')
                    return HttpResponseRedirect(raw_next_url)
        else:
            if uidb64 and token:
                uid = urlsafe_base64_decode(uidb64)
                member = authenticate(uid=uid)
                if token == member.password[-TOKEN_CHUNK:-1]:
                    login(request, member)