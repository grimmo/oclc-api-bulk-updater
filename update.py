#!/usr/bin/env python3
# Modifica anagrafica WMS OCLC via API
# Forked from https://github.com/larrydeck/oclc-api-bulk-updater
# luigi.messina@unimib.it

import json
from base64 import b64encode
from os.path import exists
import sys
import pyjq
import requests
from dotenv import dotenv_values
from time import sleep


if exists('.env'):
    config = dotenv_values('.env')
else:
    sys.exit('.env file not found, exiting')

try:
    WSKEY   = config['WSKEY']
    SECRET  = config['SECRET']
    INSTID  = config['INSTID']
except KeyError:
    sys.exit('one or more of the expected variables not found in .env file, exiting')

combo       = WSKEY+':'+SECRET
auth        = combo.encode()
authenc     = b64encode(auth)
authheader  = { 'Authorization' : 'Basic %s' %  authenc.decode() }
# Per anagrafica lo scope deve essere SCIM
url         = "https://oauth.oclc.org/token?grant_type=client_credentials&scope=SCIM"
BASEURL = "https://%s.share.worldcat.org/idaas/scim/v2" %INSTID
SEARCHURL = BASEURL + '/Users/.search'

def getToken():
    "Ottiene un token da OCLC"
    try:
        r = requests.post(url, headers=authheader)
        r.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise SystemExit(err)

    return r.json()['access_token']


def searchPatron(patronBarcode, authtoken):
    "Cerca un patron dato un barcode ed un token di autenticazione"
    search  = '''
        {
            "schemas": [ "urn:ietf:params:scim:api:messages:2.0:SearchRequest" ]
            , "filter": "External_ID eq \\"%s\\"" 
        }
        ''' % patronBarcode

    searchheaders = { 
        'Authorization' : 'Bearer %s' % authtoken
        , 'Content-Type' : 'application/scim+json'
        , 'Accept' : 'application/scim+json' 
    }

    try:
        s = requests.post(SEARCHURL, headers=searchheaders, data=search)
        s.raise_for_status()
    except requests.exceptions.HTTPError as err:
        if s.status_code == 401:
            raise ValueError('Token expired')
        else:
            SystemExit(err)

    return pyjq.first('.Resources[0].id', s.json())


def readPatron(userId, authtoken):
    "Recupera la scheda utente in formato Json dato uno userid e un token"
    # Lo userId corrisponde al campo PPID visibile nella sezione Diagnostica
    # della GUI di WMS

    readurl = BASEURL + '/Users/%s' % userId

    readheaders = {
        'Authorization' : 'Bearer %s' % authtoken
        , 'Accept' : 'application/scim+json' 
    }

    try:
        read = requests.get(readurl, headers=readheaders)
        read.raise_for_status()
    except requests.exceptions.HTTPError as err:
        if read.status_code == 401:
            raise ValueError('Token expired')
        else:
            SystemExit(err)
        
    return read

def updatePatron(userId, moddedRecord, etag, authtoken):
    "Modifica un record utente passando un json contenente la nuova scheda"

    updateUrl = BASEURL + '/Users/%s' % userId

    updateheaders =  {
        'Authorization' : 'Bearer %s' % authtoken
        , 'Accept' : 'application/scim+json' 
        , 'Content-Type' : 'application/scim+json' 
        , 'If-Match' : etag
    }

    try:
        update = requests.put(updateUrl, headers=updateheaders, data=moddedRecord)
        update.raise_for_status()
    except requests.exceptions.HTTPError as err:
        if update.status_code == 401:
            raise ValueError('Token expired')
        else:
            SystemExit(err)

    return update

if __name__ == "__main__":

    # File .env contiene WSKEY, SECRET e INSTITUTION ID
    # che sono specifici per ogni cliente e devono restare segreti
    
    # Read mod.jq for modifier
    
    with open('mod.idm.jq', 'r') as file:
        MODJQ = file.read()
    #MODJQ = '."urn:mace:oclc.org:eidm:schema:persona:persona:20180305".oclcExpirationDate = "2035-12-30T00:00:00Z"'
    # MODJQ = '.'
    
    
    
    # old token to test refresh
    # TOKEN = "tk_vziB66LUGsTrc0MRpml5yo4VYoKWUPTvUXfj"
    
    TOKEN = getToken()
    
    
    # LOOP
    # take identifiers from stdin
    
    for line in sys.stdin:
        barcode = line.strip()
    
        if barcode == "":
            # ignore blanks! 
            pass
        else:
            # find patron's PPID using barcode
            try:
                ppid =  searchPatron(barcode, TOKEN)
            except ValueError:
                # token has expired, get a fresh token and redo search
                print('getting new token')
                TOKEN = getToken()
                ppid =  searchPatron(barcode, TOKEN)
    
            try:
                patron = readPatron(ppid, TOKEN)
                # for debugging
                patronJson = json.dumps(patron.json())
                #print(patronJson)
            except ValueError:
                # token has expired, get a fresh token and redo read
                print('getting new token')
                TOKEN = getToken()
                patron = readPatron(ppid, TOKEN)
    
            # Extract ETag for safe update
            ETag = patron.headers['ETag']
    
            # Create modded record with MODJQ
            modded = json.dumps(pyjq.one(MODJQ, patron.json()))
            #print(modded)
    
            # Update patron record
            try:
                update = updatePatron(ppid, modded, ETag, TOKEN)
                # print simple confirmation
                print(str(barcode) + "\t" + str(update.status_code))
            except ValueError:
                # token has expired, get a fresh token and redo update
                print('update getting new token')
                TOKEN = getToken()
                update = updatePatron(ppid, modded, ETag, TOKEN)
            # Evita di superare i limiti di interrogazione delle API
            # solo per cautela
            sleep(5)
