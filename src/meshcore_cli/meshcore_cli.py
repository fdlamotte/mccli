#!/usr/bin/python
""" 
    mccli.py : CLI interface to MeschCore BLE companion app
"""
import asyncio
import os
import sys
import getopt
import json
import datetime
import time
from pathlib import Path

from meshcore import TCPConnection
from meshcore import BLEConnection
from meshcore import SerialConnection
from meshcore import printerr
from meshcore import MeshCore

# default address is stored in a config file
MCCLI_CONFIG_DIR = str(Path.home()) + "/.config/mc-cli/"
MCCLI_ADDRESS = MCCLI_CONFIG_DIR + "default_address"

# Fallback address if config file not found
# if None or "" then a scan is performed
ADDRESS = ""

async def next_cmd(mc, cmds):
    """ process next command """
    argnum = 0
    match cmds[0] :
        case "q":
            print(await mc.send_device_qeury())
        case "get_time" | "clock" :
            if len(cmds) > 1 and cmds[1] == "sync" :
                argnum=1
                print(await mc.set_time(int(time.time())))
            else:
                timestamp = await mc.get_time()
                print('Current time :'
                    f' {datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")}'
                    f' ({timestamp})')
        case "sync_time"|"clock sync"|"st":
            print(await mc.set_time(int(time.time())))
        case "set_time" :
            argnum = 1
            print(await mc.set_time(cmds[1]))
        case "set_txpower"|"txp" :
            argnum = 1
            print(await mc.set_tx_power(cmds[1]))
        case "set_radio"|"rad" :
            argnum = 4
            print(await mc.set_radio(cmds[1], cmds[2], cmds[3], cmds[4]))
        case "set_name" :
            argnum = 1
            print(await mc.set_name(cmds[1]))
        case "set":
            argnum = 2
            match cmds[1]:
                case "pin":
                    print (await mc.set_devicepin(cmds[2]))
                case "radio":
                    params=cmds[2].split(",")
                    print (await mc.set_radio(params[0], params[1], params[2], params[3]))
                case "name":
                    print (await mc.set_name(cmds[2]))
                case "tx":
                    print (await mc.set_tx_power(cmds[2]))
                case "lat":
                    print (await mc.set_coords(\
                            float(cmds[2]),\
                            mc.self_infos['adv_lon']))
                case "lon":
                    print (await mc.set_coords(\
                            mc.self_infos['adv_lat'],\
                            float(cmds[2])))
                case "coords":
                    params=cmds[2].split(",")
                    print (await mc.set_coords(\
                            float(params[0]),\
                            float(params[1])))
        case "set_tuning"|"tun" :
            argnum = 2
            print(await mc.set_tuning(cmds[1], cmds[2]))
        case "get_bat" | "b":
            print(await mc.get_bat())
        case "reboot" :
            print(await mc.reboot())
        case "send" :
            argnum = 2
            print(await mc.send_msg(bytes.fromhex(cmds[1]), cmds[2]))
        case "msg" | "sendto" | "m" | "{" : # sends to a contact from name
            argnum = 2
            await mc.ensure_contacts()
            print(await mc.send_msg(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])[0:6],
                                    cmds[2]))
        case "chan_msg"|"ch" :
            argnum = 2
            print(await mc.send_chan_msg(cmds[1], cmds[2]))
        case "def_chan_msg"|"def_chan"|"dch" : # default chan
            argnum = 1
            print(await mc.send_chan_msg(0, cmds[1]))
        case "cmd" | "c" | "[" :
            argnum = 2
            await mc.ensure_contacts()
            print(await mc.send_cmd(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])[0:6],
                                    cmds[2]))
        case "login" | "l" | "[[" :
            argnum = 2
            await mc.ensure_contacts()
            print(await mc.send_login(bytes.fromhex(mc.contacts[cmds[1]]["public_key"]),
                                    cmds[2]))
        case "wait_login" | "wl" | "]]":
            print(await mc.wait_login())
        case "req_status" | "rs" :
            argnum = 1
            await mc.ensure_contacts()
            print(await mc.send_statusreq(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])))
        case "wait_status" | "ws" :
            print(await mc.wait_status())
        case "contacts" | "lc":
            print(json.dumps(await mc.get_contacts(),indent=4))
        case "change_path" | "cp":
            argnum = 2 
            await mc.ensure_contacts()
            await mc.set_out_path(mc.contacts[cmds[1]], cmds[2])
            print(await mc.update_contact(mc.contacts[cmds[1]]))
        case "reset_path" | "rp" :
            argnum = 1
            await mc.ensure_contacts()
            print(await mc.reset_path(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])))
            await mc.get_contacts()
        case "share_contact" | "sc":
            argnum = 1
            await mc.ensure_contacts()
            print(await mc.share_contact(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])))
        case "export_contact"|"ec":
            argnum = 1
            await mc.ensure_contacts()
            print(await mc.export_contact(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])))
        case "export_myself"|"e":
            print(await mc.export_contact())
        case "remove_contact" :
            argnum = 1
            await mc.ensure_contacts()
            print(await mc.remove_contact(bytes.fromhex(mc.contacts[cmds[1]]["public_key"])))
        case "recv" | "r" :
            print(await mc.get_msg())
        case "sync_msgs" | "sm":
            res=True
            while res:
                res = await mc.get_msg()
                print (res)
        case "wait_msg" | "wm" :
            await mc.wait_msg()
            res = await mc.get_msg()
            print (res)
        case "trywait_msg" | "wmt" :
            argnum = 1
            if await mc.wait_msg(timeout=int(cmds[1])) :
                print (await mc.get_msg())
        case "wmt8"|"]":
            if await mc.wait_msg(timeout=8) :
               print (await mc.get_msg()) 
        case "wait_ack" | "wa" | "}":
            await mc.wait_ack()
        case "infos" | "i" :
            print(json.dumps(mc.self_info,indent=4))
        case "advert" | "a":
            print(await mc.send_advert())
        case "sleep" | "s" :
            argnum = 1
            await asyncio.sleep(int(cmds[1]))

    printerr (f"cmd {cmds[0:argnum+1]} processed ...")
    return cmds[argnum+1:]

def usage () :
    """ Prints some help """
    print("""mccli.py : CLI interface to MeschCore BLE companion app

   Usage : mccli.py <args> <commands>

 Arguments :
    -h : prints this help
    -a <address>    : specifies device address (can be a name)
    -d <name>       : filter meshcore devices with name or address
    -t <hostname>   : connects via tcp/ip
    -p <port>       : specifies tcp port (default 5000)
    -s <port>       : use serial port <port>
    -b <baudrate>   : specify baudrate

 Available Commands and shorcuts (can be chained) :
    infos                  : print informations about the node      i 
    reboot                 : reboots node                             
    send <key> <msg>       : sends msg to node using pubkey[0:6]
    sendto <name> <msg>    : sends msg to node with given name        
    msg <name> <msg>       : same as sendto                         m 
    wait_ack               : wait an ack for last sent msg          wa
    recv                   : reads next msg                         r 
    sync_msgs              : gets all unread msgs from the node     sm
    wait_msg               : wait for a message and read it         wm
    advert                 : sends advert                           a 
    contacts               : gets contact list                      lc
    share_contact <ct>     : share a contact with others            sc
    remove_contact <ct>    : removes a contact from this node         
    reset_path <ct>        : resets path to a contact to flood      rp
    change_path <ct> <path>: change the path to a contact           cp
    get_time               : gets current time                        
    set_time <epoch>       : sets time to given epoch                 
    sync_time              : sync time with system                    
    set_name <name>        : sets node name                           
    get_bat                : gets battery level                     b 
    login <name> <pwd>     : log into a node (rep) with given pwd   l 
    wait_login             : wait for login (timeouts after 5sec)   wl
    cmd <name> <cmd>       : sends a command to a repeater (no ack) c 
    req_status <name>      : requests status from a node            rs
    wait_status            : wait and print reply                   ws
    sleep <secs>           : sleeps for a given amount of secs      s""") 
                        
async def main(argv):   
    """ Do the job """  
    address = ADDRESS
    port = 5000
    hostname = None
    serial_port = None
    baudrate = 115200
    # If there is an address in config file, use it by default
    # unless an arg is explicitely given
    if os.path.exists(MCCLI_ADDRESS) :
        with open(MCCLI_ADDRESS, encoding="utf-8") as f :
            address = f.readline().strip()

    opts, args = getopt.getopt(argv, "a:d:s:ht:p:b:")
    for opt, arg in opts :
        match opt:
            case "-d" : # name specified on cmdline
                address = arg
            case "-a" : # address specified on cmdline
                address = arg
            case "-s" : # serial port
                serial_port = arg
            case "-b" :
                baudrate = int(arg)
            case "-t" : 
                hostname = arg
            case "-p" :
                port = int(arg)

    if len(args) == 0 : # no args, no action
        usage()
        return

    con = None
    if not hostname is None : # connect via tcp
        con = TCPConnection(hostname, port)
        await con.connect() 
    elif not serial_port is None : # connect via serial port
        con = SerialConnection(serial_port, baudrate)
        await con.connect()
        await asyncio.sleep(0.1)
    else : #connect via ble
        con = BLEConnection(address)
        address = await con.connect()
        if address is None or address == "" : # no device, no action
            printerr ("No device found, exiting ...")
            return

        # Store device address in configuration
        if os.path.isdir(MCCLI_CONFIG_DIR) :
            with open(MCCLI_ADDRESS, "w", encoding="utf-8") as f :
                f.write(address)

    mc = MeshCore(con)
    await mc.connect()

    cmds = args
    while len(cmds) > 0 :
        cmds = await next_cmd(mc, cmds)

def cli():
    asyncio.run(main(sys.argv[1:]))
