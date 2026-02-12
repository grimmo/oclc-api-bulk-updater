# -*- coding: utf-8 -*-
# Copyright (c) 2026 Università degli Studi di Milano Bicocca
# Tutti i diritti riservati
# luigi.messina@unimib.it

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter, Retry
import yaml
import tempfile
import lxml.etree as ET
import csv
import logging


class OCLCException(Exception):
    "Classe per logging automatico delle eccezioni"
    def __init__(self, msg=''):
        self.msg = msg
        logger = logging.getLogger(__name__)
        logger.critical(msg)

    def __str__(self):
        return self.msg
    pass


class TokenRenewException(OCLCException):
    pass

class NoPreviousTokenExists(OCLCException):
    pass

class TokenExpiredException(OCLCException):
    pass


def leggi_configurazione(file_config):
    try:
        with open(file_config, 'r') as stream:
            config = yaml.safe_load(stream)
    except FileNotFoundError:
        logging.critical('Impossibile trovare il file di configurazione {file_config}')
        raise
    except PermissionError:
        logging.critical('Impossibile trovare il file di configurazione {file_config}')
        raise
    except:
        logging.critical('Errore inaspettato durante la lettura del file di configurazione {file_config}')
        raise
    else:
        return config


def _interroga_api(api_url,api_call_headers):
    log = logging.getLogger(__name__)
    query_url = api_url
    return session.get(query_url, headers=api_call_headers, verify=False)

def _save_token(t):
    "Given a token, saves it on tokenfile in YAML format"
    logger = logging.getLogger(__name__)
    tokenfile = tempfile.NamedTemporaryFile(prefix='wms_token',mode='w', buffering=- 1, delete=False)
    logger.debug('Scrivo il token %s nel file %s' % (t,tokenfile.name))
    yaml.safe_dump(t, tokenfile)
    tokenfile.close()
    logger.debug(f'Token salvato con successo in {tokenfile}')
    return tokenfile.name

def _update_config_tokenfile(tokenfile,configfile='config.yml'):
    "Aggiorna il path del file contenente il token nel file di configurazione"
    logger = logging.getLogger(__name__)
    try:
        config = leggi_configurazione(configfile)
    except:
        raise
    else:
        logger.debug('Memorizzo il nome del file che contiene il token {tokenfile} in {configfile}')
    try:
        config['tokenfile'] = tokenfile
        with open(configfile,'w') as stream:
            yaml.safe_dump(config, stream)
    except PermissionError:
        raise
    except TypeError:
        # Probabilmente non esiste il file di configurazione
        raise('Unable to read config file {configfile} no update performed')
    else:
        logger.info('Token file location successfully updated')

def _get_token_from_file(tokenfile):
    "Recupera un token salvato in formato YAML da tokenfile"
    logger = logging.getLogger(__name__)
    try:
        with open(tokenfile, 'r') as f:
            token = yaml.safe_load(f)
    except FileNotFoundError:
        logger.debug(f"Failed to retrieve existing token from {tokenfile}")
        raise NoPreviousTokenExists(f'File not found {tokenfile}')
    except PermissionError:
        raise
    except:
        logger.critical(f'Unexpected exception in _get_token_from_file({tokenfile})')
        raise
    else:
        return token

def _new_token_from_oclc(session,auth_server_url,client_id,client_secret,grant_type,scope):
    #auth_server_url = config['auth_server_url']
    #client_id = config.get('client_id')
    #client_secret = config.get('client_secret')
    #token_req_payload = {'grant_type': 'client_credentials','scope':'WMS_COLLECTION_MANAGEMENT'}
    logger = logging.getLogger(__name__)
    token_request_parameters = {'grant_type': grant_type,'scope':scope}
    logger.debug('Invio richiesta di un nuovo token di sessione al server OCLC')
    logger.debug(f'client_id: {client_id} client_secret: {client_secret} grant_type: {grant_type} scope: {scope}')
    try:
        token_response = session.post(auth_server_url, data=token_request_parameters, allow_redirects=False, timeout=60, auth=(client_id, client_secret))
    except requests.exceptions.Timeout:
        logger.error('Token request timed out')
    except (requests.ConnectionError, e):
        logger.critical(f'Unable to connect to OCLC server at {auth_server_url} to request a new token, error: {e}')
    else:
        #new_token_requested.set()
        logger.debug('Risposta dal server WMS: %s' % token_response)
        if token_response.status_code !=200:
            logger.critical('Impossibile ottenere nuovo token da WMS %s' % token_response.status_code)
            raise TokenRenewException('Error getting new token from OCLC.',f'Status code: {token_response.status_code}')
        else:
            logger.debug("Successfuly obtained a new token %s" % token_response.text )
            return token_response.text
            #tokens = json.loads(token_response.text)
            # Salva il token
            #return tokens['access_token']

def get_token(configfile='config.yml',session=None):
    "Ritorna un token di sessione per le API OCLC, recuperandolo da file oppure chiedendone uno nuovo"
    logger = logging.getLogger(__name__)
    config = leggi_configurazione(configfile)
    # Prova a recuperare un token già esistente da file
    try:
        logger.debug(f"Attempting to retrieve existing token from {config['tokenfile']}...")
        token = _get_token_from_file(config['tokenfile'])
    except KeyError:
        logger.info("Previous token file location missing, first run?")
    except NoPreviousTokenExists:
        logger.info(f"Failed to retrieve existing token from {config['tokenfile']}")
    else:
        logger.debug(f"Successfully obtained previous token")
        return token
    if not session:
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=1,status_forcelist=[ 500, 502, 503, 504 ])
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            proxies = {'http': config['proxy_url'],'https':config['proxy_url']}
        except KeyError:
            # Proxy non configurato, connessione diretta
            pass
        else:
            session.proxies = proxies
            logger.warning('Attenzione, le connessioni verranno effettuate attraverso il proxy: {proxies}')
    token = _new_token_from_oclc(session,config['auth_server_url'],config['client_id'],config['client_secret'],config['grant_type'],config['scope'])
    new_tokenfile = _save_token(token)
    _update_config_tokenfile(new_tokenfile,configfile=configfile)
    return token


if __name__ == "__main__()":
    rf = RotatingFileHandler(filename='oclc_api.log',mode='a',maxBytes=10*1024*1024,backupCount=1,encoding='utf-8',delay=0)
    frmt = logging.Formatter('[%(asctime)s - %(threadName)s - %(levelname)s]: %(message)s',datefmt="%d-%m-%Y %H:%M:%S")
    rf.setFormatter(frmt)
    logger = logging.getLogger('oclc_api')
    logger.addHandler(rf)
    logger.setLevel(logging.DEBUG)
    # Crea oggetto sessione per le query
    #session = requests.Session()
    # retries serve ad evitare timeout con squid
    #auth_url= "https://oauth.oclc.org/token"
    #c_id = "crkqL7rNmD9hpzuvE5Ejo6Se7CoOdej7H5oqfORUFwY6ONGKqXLMkSgplGRhmsP5LX8FPeNt3NdjVwMJ"
    #c_secr = "KXUofpVOrM2Z9uo8re+FDc8/9y5ZFYzF"
    #gtype = 'client_credentials'
    #scope = 'WMS_COLLECTION_MANAGEMENT'
    #_new_token_from_oclc(session,auth_url,c_id,c_secr,gtype,scope)
