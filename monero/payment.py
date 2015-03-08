#!/bin/python
#
# python-monero - payment
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
import time
from log import log_error, log_warn, log_info, log_log
from utils import *
from redisdb import *

def GetWalletAddress(wallet_host,wallet_port):
  try:
    j = SendJSONRPCCommand(wallet_host,wallet_port,"getaddress",None)
    if not "result" in j:
      log_error('GetWalletAddress: No result found in getaddress reply')
      return None
    result = j["result"]
    if not "address" in result:
      log_error('GetWalletAddress: No address found in getaddress reply')
      return None
    return result["address"]
  except Exception,e:
    log_error("GetWalletAddress: Error retrieving wallet address: %s" % (str(e)))
    return None

def UpdateCoin(daemon_host,daemon_port,wallet_host,wallet_port,full_history=False,paymentid=None,config_confirmations=6):
  txs=[]
  executed_txs=[]

  try:
    try:
      if full_history:
        scan_block_height = 0
      else:
        scan_block_height = redis_get("scan_block_height")
        scan_block_height = long(scan_block_height)
    except Exception,e:
      log_error('Failed to get scan_block_height: %s' % str(e))
      return None

    try:
      j = SendHTMLCommand(daemon_host,daemon_port,"getheight")
    except Exception,e:
      log_error('UpdateCoin: error getting height: %s' % str(e))
      return None
    if not "height" in j:
      log_error('UpdateCoin: error getting height: height not found in %s' % str(j))
      return None
    try:
      height=long(j["height"])
    except Exception,e:
      log_error('UpdateCoin: error getting height: %s' % str(e))
      return None

    if paymentid != None:
      if isinstance(paymentid,list):
        payment_ids = paymentid
      else:
        payment_ids = [paymentid]
    else:
      full_payment_ids = redis_hgetall("paymentid")
      #print 'Got full payment ids: %s' % str(full_payment_ids)
      payment_ids = []
      for pid in full_payment_ids:
        payment_ids.append(pid)

    #print 'Got payment ids: %s' % str(payment_ids)
    params = {
      "payment_ids": payment_ids,
      "min_block_height": scan_block_height
    }
    j = SendJSONRPCCommand(wallet_host,wallet_port,"get_bulk_payments",params)
    #print 'Got j: %s' % str(j)
    if "result" in j:
      result = j["result"]
      cp = redis_pipeline()
      if not full_history:
        cp.delete('confirming_payments')
      if "payments" in result:
        payments = result["payments"]
        new_payments = []
        n_confirming = 0
        new_scan_block_height = scan_block_height
        for p in payments:
          payment_id=p["payment_id"]
          tx_hash = p["tx_hash"]
          bh = p["block_height"]
          ut = p["block_height"]
          amount=p["amount"]
          if not full_history and redis_sismember("processed_txs",tx_hash):
            continue
          log_log('UpdateCoin: Looking at payment %s' % str(p))
          confirmations = height-1-bh
          confirmations_needed = max(config_confirmations,ut-height)
          if confirmations >= confirmations_needed:
            log_info('Payment %s is now confirmed' % str(p))
            new_payments.append(p)
            if new_scan_block_height and bh > new_scan_block_height:
              new_scan_block_height = bh
          else:
            log_info('Payment %s has %d/%d confirmations' % (str(p),confirmations,confirmations_needed))
            n_confirming += 1
            new_scan_block_height = None
            try:
              recipient = GetUserIDFromPaymentID(payment_id)
              if not recipient:
                raise RuntimeError('Payment ID %s not found' % payment_id)
              log_info('UpdateCoin: Found payment %s to %s for %s' % (tx_hash,recipient, AmountToString(amount)))
              if not full_history:
                cp.hincrby('confirming_payments',recipient,amount)
              txs.append({'tx_hash':tx_hash,'amount':amount,'confirmed':False,'confirmations':confirmations,'payment_id':payment_id,'recipient':recipient})
            except Exception,e:
              log_error('UpdateCoin: No identity found for payment id %s, tx hash %s, amount %s: %s' % (payment_id, tx_hash, amount, str(e)))
        payments=new_payments
        log_info('UpdateCoin: Got %d mature payments and %d confirming payments' % (len(payments),n_confirming))
        if len(payments) > 0:
          if not full_history and new_scan_block_height and new_scan_block_height > scan_block_height:
            scan_block_height = new_scan_block_height
            log_log('UpdateCoin: increasing scan_block_height to %d' % scan_block_height)
          try:
            pipe = redis_pipeline()
            if not full_history:
              pipe.set("scan_block_height", scan_block_height)
            log_log('UpdateCoin: processing payments')
            for p in payments:
              payment_id=p["payment_id"]
              tx_hash=p["tx_hash"]
              amount=p["amount"]
              bh = p["block_height"]
              ut = p["unlock_time"]
              confirmations = height-1-bh
              try:
                recipient = GetUserIDFromPaymentID(payment_id)
                if not recipient:
                  raise RuntimeError('Payment ID %s not found' % payment_id)
                log_info('UpdateCoin: Found payment %s to %s for %s' % (tx_hash,recipient, AmountToString(amount)))
                if not full_history:
                  pipe.sadd("processed_txs",tx_hash)
                txs.append({'tx_hash':tx_hash,'amount':amount,'confirmed':True,'confirmations':confirmations,'payment_id':payment_id,'recipient':recipient})
              except Exception,e:
                log_error('UpdateCoin: No identity found for payment id %s, tx hash %s, amount %s: %s' % (payment_id, tx_hash, amount, str(e)))
            log_log('UpdateCoin: Executing received payments pipeline')
            if not full_history:
              pipe.execute()
          except Exception,e:
            log_error('UpdateCoin: failed to set scan_block_height: %s' % str(e))
      if not full_history:
        cp.execute()
      executed_txs=txs
    else:
      log_error('UpdateCoin: No results in get_bulk_payments reply')
  except Exception,e:
    log_error('UpdateCoin: Failed to get bulk payments: %s' % str(e))
  return executed_txs

def SendMany(wallet_host,wallet_port,recipients,paymentid=None,mixin=None):
  for address in recipients:
    if not IsValidAddress(address):
      log_error("Invalid address: %s" % address)
      return
    amount = recipients[address]
    if amount <= 0:
      log_error("Invalid amount: %s" % str(amount))
      return

  if paymentid != None:
    if not IsValidPaymentID(paymentid):
      log_error("Invalid payment ID")
      return

  if mixin < 0:
    log_error("Invalid mixin: %d")
    return

  log_info("Pay: sending %s, payment id %s, mixin %d" % (str(recipients), str(paymentid),mixin))

  try:
    destinations=[]
    for address in recipients:
      destinations.append({'address':address,'amount':recipients[address]})
    params = {
      'destinations':destinations,
      'payment_id': paymentid,
      'fee': 0,
      'mixin': mixin,
      'unlock_time': 0,
    }
    j = SendJSONRPCCommand(wallet_host,wallet_port,"transfer",params)
  except Exception,e:
    log_error('Withdraw: Error in transfer: %s' % str(e))
    return
  if not "result" in j:
    log_error('Withdraw: No result in transfer reply')
    return
  result = j["result"]
  if not "tx_hash" in result:
    log_error('Withdraw: No tx_hash in transfer reply')
    return
  tx_hash = result["tx_hash"]
  log_info('tx sent, tx_hash %s' % (str(tx_hash)))
  return tx_hash

def Send(wallet_host,wallet_port,address,amount,paymentid=None,mixin=None):
  return SendMany(wallet_host,wallet_port,{address: amount},paymentid,mixin)

def CheckForDeposits(daemon_host,daemon_port,wallet_host,wallet_port,confirmations):
  return UpdateCoin(daemon_host,daemon_port,wallet_host,wallet_port,full_history=False,config_confirmations=confirmations)

def GetDepositHistory(daemon_host,daemon_port,wallet_host,wallet_port,paymentid=[]):
  return UpdateCoin(daemon_host,daemon_port,wallet_host,wallet_port,full_history=True,paymentid=paymentid)

