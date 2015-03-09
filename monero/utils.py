#!/bin/python
#
# python-monero - utility functions
# Copyright 2014,2015 moneromooo
#
# Redistribution and use in source and binary forms, with or without modification, are
# permitted provided that the following conditions are met:
# 
# 1. Redistributions of source code must retain the above copyright notice, this list of
#    conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright notice, this list
#    of conditions and the following disclaimer in the documentation and/or other
#    materials provided with the distribution.
# 
# 3. Neither the name of the copyright holder nor the names of its contributors may be
#    used to endorse or promote products derived from this software without specific
#    prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
# THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
# THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import redis
import hashlib
import json
import httplib
import time
import string
from Crypto.Random.random import getrandbits
from decimal import *
from log import log_error, log_warn, log_info, log_log
from redisdb import *

address_length = [95, 95] # min/max size of addresses
address_prefix = ['4', '9'] # allowed prefixes of addresses

cached_wallet_balance=None
cached_wallet_unlocked_balance=None
cached_wallet_balance_timestamp=None

def GetPaymentIDFromUserID(user_id,deterministic,site_salt=''):
  salt="nveuweaiirv-"+site_salt+'-'
  if deterministic:
    s = salt + user_id
  else:
    s = salt + str(getrandbits(128)) + '-' + user_id
  p = hashlib.sha256(s).hexdigest()
  try:
    redis_hset("paymentid",p,user_id)
  except Exception,e:
    log_error('GetPaymentIDFromUserID: failed to set payment ID for %s to redis: %s' % (user_id,str(e)))
  return p

def GetUserIDFromPaymentID(paymentid):
  if not redis_hexists("paymentid",paymentid):
    log_log('PaymentID %s not found' % paymentid)
    return None
  identity = redis_hget("paymentid",paymentid)
  log_log('PaymentID %s => %s' % (paymentid, str(identity)))
  return identity


def IsValidAddress(address):
  if len(address) < address_length[0] or len(address) > address_length[1]:
    return False
  for prefix in address_prefix:
    if address.startswith(prefix):
      return True
  return False

def IsValidPaymentID(payment_id):
  if len(payment_id)!=64:
    return False
  for char in payment_id:
    if char not in string.hexdigits:
      return False
  return True

def SendJSONRPCCommand(host,port,method,params):
  try:
    http = httplib.HTTPConnection(host,port,timeout=20)
  except Exception,e:
    log_error('SendJSONRPCCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  d = dict(id="0",jsonrpc="2.0",method=method,params=params)
  try:
    j = json.dumps(d).encode()
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to encode JSON: %s' % str(e))
    http.close()
    raise
  log_log('SendJSONRPCCommand: Sending json as body: %s' % j)
  headers = None
  try:
    http.request("POST","/json_rpc",body=j)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  if response.status != 200:
    log_error('SendJSONRPCCommand: Error, received reply status %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendJSONRPCCommand: Received reply status %s: %s' % (response.status, str(s).replace('\r\n',' ').replace('\n',' ')))
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to decode JSON: %s' % str(e))
    http.close()
    raise
  http.close()
  return j

def SendHTMLCommand(host,port,method):
  try:
    http = httplib.HTTPConnection(host,port,timeout=20)
  except Exception,e:
    log_error('SendHTMLCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  headers = None
  try:
    http.request("POST","/"+method)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  if response.status != 200:
    log_error('SendHTMLCommand: Error, received reply status %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendHTMLCommand: Received reply status %s: %s' % (response.status,s.replace('\r\n',' ').replace('\n',' ')))
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to decode JSON: %s' % str(e))
    http.close()
    raise
  http.close()
  return j

def RetrieveWalletBalance(wallet_host,wallet_port,force_refresh=False):
  global cached_wallet_balance, cached_wallet_unlocked_balance, cached_wallet_balance_timestamp
  if not force_refresh and cached_wallet_balance_timestamp and time.time()-cached_wallet_balance_timestamp < 35:
    return cached_wallet_balance, cached_wallet_unlocked_balance

  j = SendJSONRPCCommand(wallet_host,wallet_port,"getbalance",None)
  if not "result" in j:
    log_error('RetrieveWalletBalance: result not found in reply')
    raise RuntimeError("")
    return
  result = j["result"]
  if not "balance" in result:
    log_error('RetrieveWalletBalance: balance not found in result')
    raise RuntimeError("")
    return
  if not "unlocked_balance" in result:
    log_error('RetrieveWalletBalance: unlocked_balance not found in result')
    raise RuntimeError("")
    return
  balance = result["balance"]
  unlocked_balance = result["unlocked_balance"]
  log_log('RetrieveWalletBalance: balance: %s' % str(balance))
  log_log('RetrieveWalletBalance: unlocked_balance: %s' % str(unlocked_balance))
  pending = long(balance)-long(unlocked_balance)
  if pending < 0:
    log_error('RetrieveWalletBalance: Negative pending balance! balance %s, unlocked %s' % (str(balance),str(unlocked_balance)))
    raise RuntimeError("")
    return
  cached_wallet_balance_timestamp=time.time()
  cached_wallet_balance=balance
  cached_wallet_unlocked_balance=unlocked_balance
  return balance, unlocked_balance

# Code taken from the Python documentation
def moneyfmt(value, places=2, curr='', sep=',', dp='.',
             pos='', neg='-', trailneg=''):
    """Convert Decimal to a money formatted string.

    places:  required number of places after the decimal point
    curr:    optional currency symbol before the sign (may be blank)
    sep:     optional grouping separator (comma, period, space, or blank)
    dp:      decimal point indicator (comma or period)
             only specify as blank when places is zero
    pos:     optional sign for positive numbers: '+', space or blank
    neg:     optional sign for negative numbers: '-', '(', space or blank
    trailneg:optional trailing minus indicator:  '-', ')', space or blank

    >>> d = Decimal('-1234567.8901')
    >>> moneyfmt(d, curr='$')
    '-$1,234,567.89'
    >>> moneyfmt(d, places=0, sep='.', dp='', neg='', trailneg='-')
    '1.234.568-'
    >>> moneyfmt(d, curr='$', neg='(', trailneg=')')
    '($1,234,567.89)'
    >>> moneyfmt(Decimal(123456789), sep=' ')
    '123 456 789.00'
    >>> moneyfmt(Decimal('-0.02'), neg='<', trailneg='>')
    '<0.02>'

    """
    q = Decimal(10) ** -places      # 2 places --> '0.01'
    sign, digits, exp = value.quantize(q).as_tuple()
    result = []
    digits = map(str, digits)
    build, next = result.append, digits.pop
    if sign:
        build(trailneg)
    for i in range(places):
        build(next() if digits else '0')
    build(dp)
    if not digits:
        build('0')
    i = 0
    while digits:
        build(next())
        i += 1
        if i == 3 and digits:
            i = 0
            build(sep)
    build(curr)
    build(neg if sign else pos)
    s = ''.join(reversed(result))

    if dp in s:
      s=s.strip('0').rstrip(dp)
    if s=="" or s[0]==dp:
      s="0"+s
    return s

def AmountToString(amount):
  if amount == None:
    amount = 0
  lamount=long(amount)
  samount = moneyfmt(Decimal(lamount)/Decimal(1e12),places=12) + " monero"
  return samount

