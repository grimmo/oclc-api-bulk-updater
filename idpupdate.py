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
import pickle

ENVFILE='.env.idpupdate'
if exists(ENVFILE):
    config = dotenv_values(ENVFILE)
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
url         = "https://oauth.oclc.org/token?grant_type=client_credentials&scope=authnman:manage"
BASEURL = "https://%s.share.worldcat.org/authnman" %INSTID
#BASEURL = "https://%s.share.worldcat.org/idaas/scim/v2" %INSTID
SEARCHURL = BASEURL + '/personas/search'
RETRIES = 0 # Conta i tentativi

def _get_new_token():
    try:
        r = requests.post(url, headers=authheader)
        r.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(r.content)
        raise SystemExit(err)
    token = r.json()['access_token']
    print(f'New token obtained from OCLC: {token}')
    with open('.token.json', 'w') as f:
         token = json.dump(token, f)
         print('Token salvato per i prossimi utilizzi')
    return token

def getToken():
    "Ottiene un token da OCLC"
    print('Tentativo di acquisire un token esistente')
    try:
        with open('.token.json', 'r') as f:
            token = json.load(f)
    except:
        print('Tentativo fallito, richiedo un nuovo token')
        token = _get_new_token()
    else:
        print(f'Recuperato token esistente {token}')
    return token


def searchPatron(userId, authtoken):
    "Cerca un patron dato un barcode ed un token di autenticazione"
    global RETRIES
    search  = '''
    {
  "query": "identifier exact %s",
  "limit": 50,
  "offset": 0
}
        ''' % userId

    searchheaders = { 
        'Authorization' : 'Bearer %s' % authtoken
        , 'Content-Type' : 'application/json'
        , 'Accept' : 'application/json' 
    }

    try:
        print(f'Ricerca di {userId} su {SEARCHURL} con {search}')
        s = requests.post(SEARCHURL, headers=searchheaders, data=search)
        s.raise_for_status()
    except requests.exceptions.HTTPError as err:
        if s.status_code == 401 and RETRIES == 0:
            print('Possible token expired, requesting a fresh token...')
            TOKEN = _get_new_token()
            RETRIES+=1
            searchPatron(userId,TOKEN)
        else:
            print(s.content)
            SystemExit(err)
    except:
        print(s.content)
        raise
    print(s.content)
    return pyjq.first('.entries[0].id', s.json())


def readPatron(userId, authtoken):
    "Recupera la scheda utente in formato Json dato uno userid e un token"
    # Lo userId corrisponde al campo PPID visibile nella sezione Diagnostica
    # della GUI di WMS

    readurl = BASEURL + '/correlation-identifiers?ppid=%s' % userId

    readheaders = {
        'Authorization' : 'Bearer %s' % authtoken
        , 'Accept' : 'application/json' 
    }

    try:
        read = requests.get(readurl, headers=readheaders)
        read.raise_for_status()
    except requests.exceptions.HTTPError as err:
        if read.status_code == 401:
            raise ValueError('Token expired')
        else:
            raise err
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
            raise err
            SystemExit(err)

    return update


def deleteIdP(correlationId, authtoken):
    "Elimina correlationId da record utente"
    # Lo userId corrisponde al campo PPID visibile nella sezione Diagnostica
    # della GUI di WMS

    deleteUrl = BASEURL + '/correlation-identifiers/%s' % correlationId

    deleteHeaders = {
        'Authorization' : 'Bearer %s' % authtoken
        , 'Accept' : 'application/json' 
    }
    try:
        delete = requests.delete(deleteUrl, headers=deleteHeaders)
        print(delete.status_code)
        print(delete.content)
        delete.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise err


if __name__ == "__main__":

    # File .env contiene WSKEY, SECRET e INSTITUTION ID
    # che sono specifici per ogni cliente e devono restare segreti
    
    # Read mod.jq for modifier
    
    with open('elimina_shib.jq', 'r') as file:
        MODJQ = file.read()
    #MODJQ = '."urn:mace:oclc.org:eidm:schema:persona:persona:20180305".oclcExpirationDate = "2035-12-30T00:00:00Z"'
    # MODJQ = '.'
    print("Letto elimina_shib.jq")
    
    
    
    # old token to test refresh
    # TOKEN = "tk_vziB66LUGsTrc0MRpml5yo4VYoKWUPTvUXfj"
    print("Richiesta token...")
    
    TOKEN = getToken()
    
    
    # take identifiers from stdin
    barcode = sys.argv[1]
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
        with open("user.json","w") as user:
            user.write(json.dumps(patron.json()))
    except ValueError:
        # token has expired, get a fresh token and redo read
        print('getting new token')
        TOKEN = getToken()
        patron = readPatron(ppid, TOKEN)
    
    correlation_id_da_eliminare = pyjq.first('.entries[0].id',patron.json())
    print(f'Correlation id da eiminare {correlation_id_da_eliminare}')

    # Extract ETag for safe update
    ETag = patron.headers['ETag']
    #print(f'Patron data:\n{patron.json()}') 
    # Create modded record with MODJQ
    #modded = json.dumps(pyjq.one(MODJQ, patron.json()))
    #print(f'Modded Patron data:\n{modded}')
    #
    # Elimina record Shibboleth
    deleteIdP('229e0c35-e53a-4f19-bf05-05c94c7e9963', TOKEN)
    
    # Update patron record
    #try:
    #    update = updatePatron(ppid, modded, ETag, TOKEN)
    #    print(f"Status code: {update.status_code}")
    #except:
    #    raise
        #print(str(barcode) + "\t" + str(update.status_code))
            #except ValueError:
               # token has expired, get a fresh token and redo update
               # print('update getting new token')
            #    TOKEN = getToken()
                #update = updatePatron(ppid, modded, ETag, TOKEN)
            # Evita di superare i limiti di interrogazione delle API
            # solo per cautela
    #sleep(5)
