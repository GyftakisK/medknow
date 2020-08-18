#!/usr/bin/python
# 5/19/2016 - update to allow for authentication based on api-key, rather than username/pw
# See https://documentation.uts.nlm.nih.gov/rest/authentication.html for full explanation

import requests
import datetime
from pyquery import PyQuery as pq

uri = "https://utslogin.nlm.nih.gov"
auth_endpoint = "/cas/v1/api-key"


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class Authentication(metaclass=Singleton):

    def __init__(self, apikey):
        # self.username=username
        # self.password=password
        self.apikey = apikey
        self.service = "http://umlsks.nlm.nih.gov"
        self._tgt = None
        self._tgt_exp_time = None

    def _gettgt(self):
        # params = {'username': self.username,'password': self.password}
        params = {'apikey': self.apikey}
        h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", "User-Agent": "python" }
        r = requests.post(uri+auth_endpoint, data=params, headers=h, timeout=120)
        d = pq(r.text)
        # extract the entire URL needed from the HTML form (action attribute) returned 
        # looks similar to https://utslogin.nlm.nih.gov/cas/v1/tickets/TGT-36471-aYqNLN2rFIJPXKzxwdTNC5ZT7z3B3cTAKfSc5ndHQcUxeaDOLN-cas
        # we make a POST call to this URL in the getst method
        self._tgt = d.find('form').attr('action')
        self._tgt_exp_time = datetime.datetime.now() +  datetime.timedelta(hours=7)
        print("Got ticket")

    def getst(self):
        if not self._tgt or self._has_tgt_expired():
            self._gettgt()
        params = {'service': self.service}
        h = {"Content-type": "application/x-www-form-urlencoded", 
             "Accept": "text/plain", "User-Agent": "python"}
        r = requests.post(self._tgt, data=params, headers=h)
        st = r.text
        return st

    def _has_tgt_expired(self):
        return datetime.datetime.now() > self._tgt_exp_time
