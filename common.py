#!/usr/bin/env python
#
# common.py -- Methods used by the cloud-ha scripts.
# Created: Marcus Butler, 05-April-2017.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from boto3 import client
from botocore.exceptions import ClientError
from os import getenv
from socket import socket, AF_INET, SOCK_STREAM, IPPROTO_TCP
import sys
import json
import ssl

DBG_ERROR = 0
DBG_INFO  = 1
DBG_TRACE = 10

def DEBUG(level, message):
    if getenv('DEBUG') and int(getenv('DEBUG')) >= level:
        print(message)

def get_rtb_assoc(subnet):
    ec2 = client('ec2')
    res = ec2.describe_route_tables()

    for table in res['RouteTables']:
        for assoc in table['Associations']:
            if assoc.has_key('SubnetId') and assoc['SubnetId'] == subnet:
                return assoc['RouteTableAssociationId']

    return None

def change_rtb(old_assoc, rtb):
    ec2 = client('ec2')
    res = ec2.replace_route_table_association(AssociationId = old_assoc,
                                              RouteTableId = rtb)

    return True

def modify_route(rtb, dest, eni):
    ec2 = client('ec2')
    try:
        ec2.replace_route(RouteTableId = rtb, DestinationCidrBlock = dest, NetworkInterfaceId = eni)
    except ClientError as e:
        DEBUG(DBG_ERROR, "Unable to replace route %s on rtb %s to eni %s (error: %s)" %
                  (dest, rtb, eni, repr(e.response)))
        return False
    return True

def get_config(bucket, file):
    s3 = client('s3')

    obj = s3.get_object(Bucket=bucket, Key=file)
    dict = json.loads(obj['Body'].read())

    return dict

def check_tcp_ping(ip, port):
    s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
    s.settimeout(3)
    
    try:
        s.connect((ip, port))
    except:
        DEBUG(DBG_ERROR, "*** ERROR *** tcp_ping unable to connect to %s:%d" % (ip, port))
        s.close()
        return False

    s.close()
    return True

def check_ssl_ping(ip, port):
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.verify_mode = ssl.CERT_NONE

    s = context.wrap_socket(socket(AF_INET))
    s.settimeout(3)
    
    try:
        s.connect((ip, port))
    except:
        DEBUG(DBG_ERROR, "*** ERROR *** ssl_ping unable to connect to %s:%d" % (ip, port))
        s.close()
        return False

    s.close()
    return True

#
# check_availability -- Check the status of one or more hosts.
# Arguments:
#   config -- Configuration dictionary as returned by get_config
#   host   -- Optional argument that specifies the host to check.  If set to None, all hosts in the config
#             dictionary are checked.
#
# Return Value -- a list containing all hosts that failed their test condition(s).
#
def check_availability(config, host):
    if config is None:
        DEBUG(DBG_ERROR, 'Config not passed!')
        return False

    if not config.has_key('groups'):
        DEBUG(DBG_ERROR, 'Config does not have groups key!')
        return False

    failed_hosts = []

    for group in config['groups']:
        for device in config['groups'][group]['devices']:
            failed = False

            if not host or device.has_key(host):
                DEBUG(DBG_INFO, "Checking " + repr(device.keys()))
                for address in device[device.keys()[0]]['addresses']:
                    ip      = address['ip']
                    port    = address['port']
                    test    = address['test']
                    count   = address['count']
                    failure = address['failure']

                    DEBUG(DBG_TRACE, "Testing %s with test %s count %d/fail %d" %
                              (address['ip'], address['test'], address['count'], address['failure']))

                    if test == 'tcp_ping':
                        DEBUG(DBG_TRACE, 'Running tcp_ping for %s' % ip)
                        if check_tcp_ping(ip, int(port)) == False:
                            DEBUG(DBG_TRACE, 'tcp_ping FAILED for %s:%s' % (ip, port))

                            failed = True
                        else:
                            DEBUG(DBG_TRACE, 'tcp_ping SUCCEEDED for %s:%s' % (ip, port))
                    elif test == 'ssl_ping':
                        DEBUG(DBG_TRACE, 'Running ssl_ping for %s' % ip)
                        if check_ssl_ping(ip, int(port)) == False:
                            DEBUG(DBG_TRACE, 'ssl_ping FAILED for %s:%s' % (ip, port))

                            failed = True
                        else:
                            DEBUG(DBG_TRACE, 'ssl_ping SUCCEEDED for %s: %s' % (ip, port))
                    else:
                        DEBUG(DBG_ERROR, '*** ERROR *** Unsupported test %s specified' % ip)
            if failed == True:
                failed_hosts.append(device.keys()[0])
                DEBUG(DBG_TRACE, '*** ERROR *** One or more tests FAILED for device %s' % device.keys()[0])
            else:
                DEBUG(DBG_TRACE, 'ALL TESTS for device %s PASSED' % device.keys()[0])

    return failed_hosts

def fatal_error(errmsg):
    return {
            'statusCode': 500,
            'headers': { 'Content-Type': 'application/json' },
            'body': json.dumps({'errorMessage': errmsg})
    }
