#!/usr/bin/env python3
# Test modifica scheda utente WMS
# con JQ
# Si passa una scheda utente in JSON recuperata via API
# e si applicano le modifiche contenute nel file .jq
import json
from base64 import b64encode
from os.path import exists
import sys
import pyjq
import requests
from dotenv import dotenv_values

with open('grillo.json', 'r') as file:
    patron = json.load(file)

with open('mod.idm.jq', 'r') as file:
    MODJQ = file.read()
#MODJQ = '."urn:mace:oclc.org:eidm:schema:persona:persona:20180305".oclcExpirationDate = "2035-12-30T00:00:00Z"'
# MODJQ = '.'


#BASEURL = "https://%s.share.worldcat.org/idaas/scim/v2" %INSTID


#SEARCHURL = BASEURL + '/Users/.search'

# old token to test refresh
# TOKEN = "tk_vziB66LUGsTrc0MRpml5yo4VYoKWUPTvUXfj"

#TOKEN = getToken()


modded = json.dumps(pyjq.one(MODJQ, patron))
print(modded)

