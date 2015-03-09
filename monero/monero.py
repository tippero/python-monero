#!/bin/python
#
# python-monero
# Copyright 2015 moneromooo
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

import utils
import redisdb
import payment

class Monero:
  def __init__(self,daemon_host,daemon_port,wallet_host,wallet_port,redis_host,redis_port,site_salt):
    redisdb.connect_to_redis(redis_host,redis_port)
    self.daemon_host=daemon_host
    self.daemon_port=daemon_port
    self.wallet_host=wallet_host
    self.wallet_port=wallet_port
    self.site_salt=site_salt

  def GetWalletBalance(self):
    return utils.RetrieveWalletBalance(self.wallet_host,self.wallet_port)

  def GetPaymentID(self,recipient,deterministic=True):
    return utils.GetPaymentIDFromUserID(recipient,deterministic,self.site_salt)

  def GetRecipient(self,payment_id):
    return utils.GetUserIDFromPaymentID(payment_id)

  def CheckForDeposits(self,confirmations=6):
    return payment.CheckForDeposits(self.daemon_host,self.daemon_port,self.wallet_host,self.wallet_port,confirmations)

  def GetDepositHistory(self,paymentid=[]):
    return payment.GetDepositHistory(self.daemon_host,self.daemon_port,self.wallet_host,self.wallet_port,paymentid)

  def Send(self,address,amount,paymentid=None,mixin=3):
    return payment.Send(self.wallet_host,self.wallet_port,address,amount,paymentid,mixin)

  def SendMany(self,recipients,paymentid=None,mixin=3):
    return payment.SendMany(self.wallet_host,self.wallet_port,recipients,paymentid,mixin)

