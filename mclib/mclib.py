""" 
    mccli.py : CLI interface to MeschCore BLE companion app
"""
import asyncio
import serial_asyncio
import os
import sys
import getopt
import json
import datetime
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDeviceNotFoundError

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

def printerr (s) :
    sys.stderr.write(str(s))
    sys.stderr.write("\n")
    sys.stderr.flush()

class SerialConnection:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.frame_started = False
        self.frame_size = 0
        self.header = b""
        self.inframe = b""

    class MCSerialClientProtocol(asyncio.Protocol):
        def __init__(self, cx):
            self.cx = cx

        def connection_made(self, transport):
            self.cx.transport = transport
#            printerr('port opened')
            transport.serial.rts = False  # You can manipulate Serial object via transport
    
        def data_received(self, data):
#            printerr('data received')
            self.cx.handle_rx(data)    
    
        def connection_lost(self, exc):
            printerr('port closed')
    
        def pause_writing(self):
            printerr('pause writing')
    
        def resume_writing(self):
            printerr('resume writing')

    async def connect(self):
        """
        Connects to the device
        """
        loop = asyncio.get_running_loop()
        await serial_asyncio.create_serial_connection(
                loop, lambda: self.MCSerialClientProtocol(self), 
                self.port, baudrate=self.baudrate)

        printerr("Serial Connexion started")
        return self.port

    def set_mc(self, mc) :
        self.mc = mc

    def handle_rx(self, data: bytearray):
        headerlen = len(self.header)
        framelen = len(self.inframe)
        if not self.frame_started : # wait start of frame
            if len(data) >= 3 - headerlen:
                self.header = self.header + data[:3-headerlen]
                self.frame_started = True
                self.frame_size = int.from_bytes(self.header[1:], byteorder='little')
                self.handle_rx(data[3-headerlen:])
            else:
                self.header = self.header + data
        else:
            if framelen + len(data) < self.frame_size:
                self.inframe = self.inframe + data
            else:
                self.inframe = self.inframe + data[:self.frame_size-framelen]
                if not self.mc is None:
                    self.mc.handle_rx(self.inframe)
                self.frame_started = False
                self.header = b""
                self.inframe = b""
                if framelen + len(data) > self.frame_size:
                    self.handle_rx(data[self.frame_size-framelen:])

    async def send(self, data):
        size = len(data)
        pkt = b"\x3c" + size.to_bytes(2, byteorder="little") + data
#        printerr(f"sending pkt : {pkt}")
        self.transport.write(pkt)

class TCPConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.transport = None

    class MCClientProtocol:
        def __init__(self, cx):
            self.cx = cx

        def connection_made(self, transport):
            self.cx.transport = transport
    
        def data_received(self, data):
            self.cx.handle_rx(data)

        def error_received(self, exc):
            printerr(f'Error received: {exc}')
    
        def connection_lost(self, exc):
            printerr('The server closed the connection')

    async def connect(self):
        """
        Connects to the device
        """
        loop = asyncio.get_running_loop()
        await loop.create_connection(
                lambda: self.MCClientProtocol(self), 
                self.host, self.port)

        printerr("TCP Connexion started")
        return self.host

    def set_mc(self, mc) :
        self.mc = mc

    def handle_rx(self, data: bytearray):
        cur_data = data
        while (len(cur_data) > 0) :
            if cur_data[0] != 0x3E :
                printerr(f"Error with received frame trying anyway ... first byte is {cur_data[0]}")
        
            frame_size = int.from_bytes(cur_data[1:2], byteorder='little')
            frame = cur_data[3:3+frame_size]

            if not self.mc is None:
                self.mc.handle_rx(frame)
        
            cur_data = cur_data[3+frame_size:]

    async def send(self, data):
        size = len(data)
        pkt = b"\x3c" + size.to_bytes(2, byteorder="little") + data
        self.transport.write(pkt)

class BLEConnection:
    def __init__(self, address):
        """ Constructor : specify address """
        self.address = address
        self.client = None
        self.rx_char = None
        self.mc = None

    async def connect(self):
        """
        Connects to the device

        Returns : the address used for connection
        """
        def match_meshcore_device(_: BLEDevice, adv: AdvertisementData):
            """ Filter to mach MeshCore devices """
            if not adv.local_name is None\
                    and adv.local_name.startswith("MeshCore")\
                    and (self.address is None or self.address in adv.local_name) :
                return True
            return False

        if self.address is None or self.address == "" or len(self.address.split(":")) != 6 :
            scanner = BleakScanner()
            printerr("Scanning for devices")
            device = await scanner.find_device_by_filter(match_meshcore_device)
            if device is None :
                return None
            printerr(f"Found device : {device}")
            self.client = BleakClient(device)
            self.address = self.client.address
        else:
            self.client = BleakClient(self.address)

        try:
            await self.client.connect(disconnected_callback=self.handle_disconnect)
        except BleakDeviceNotFoundError:
            return None
        except TimeoutError:
            return None

        await self.client.start_notify(UART_TX_CHAR_UUID, self.handle_rx)

        nus = self.client.services.get_service(UART_SERVICE_UUID)
        self.rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)

        printerr("BLE Connexion started")
        return self.address

    def handle_disconnect(self, _: BleakClient):
        """ Callback to handle disconnection """
        printerr ("Device was disconnected, goodbye.")
        # cancelling all tasks effectively ends the program
        for task in asyncio.all_tasks():
            task.cancel()

    def set_mc(self, mc) :
        self.mc = mc

    def handle_rx(self, _: BleakGATTCharacteristic, data: bytearray):
        if not self.mc is None:
            self.mc.handle_rx(data)

    async def send(self, data):
        await self.client.write_gatt_char(self.rx_char, bytes(data), response=False)

class MeshCore:
    """
    Interface to a BLE MeshCore device
    """
    self_info={}
    contacts={}

    def __init__(self, cx):
        """ Constructor : specify address """
        self.time = 0
        self.result = asyncio.Future()
        self.contact_nb = 0
        self.rx_sem = asyncio.Semaphore(0)
        self.ack_ev = asyncio.Event()
        self.login_resp = asyncio.Future()
        self.status_resp = asyncio.Future()

        self.cx = cx
        cx.set_mc(self)

    async def connect(self) :
        await self.send_appstart()

    def handle_rx(self, data: bytearray):
        """ Callback to handle received data """
        match data[0]:
            case 0: # ok
                if len(data) == 5 :  # an integer
                    self.result.set_result(int.from_bytes(data[1:5], byteorder='little'))
                else:
                    self.result.set_result(True)
            case 1: # error
                if len(data) > 1:
                    self.result.set_result(data[1]) # error code if fw > 1.4
                else:
                    self.result.set_result(False)
            case 2: # contact start
                self.contact_nb = int.from_bytes(data[1:5], byteorder='little')
                self.contacts={}
            case 3: # contact
                c = {}
                c["public_key"] = data[1:33].hex()
                c["type"] = data[33]
                c["flags"] = data[34]
                c["out_path_len"] = int.from_bytes(data[35:36], signed=True)
                plen = int.from_bytes(data[35:36], signed=True)
                if plen == -1 : 
                    plen = 0
                c["out_path"] = data[36:36+plen].hex()
                c["adv_name"] = data[100:132].decode().replace("\0","")
                c["last_advert"] = int.from_bytes(data[132:136], byteorder='little')
                c["adv_lat"] = int.from_bytes(data[136:140], byteorder='little',signed=True)/1e6
                c["adv_lon"] = int.from_bytes(data[140:144], byteorder='little',signed=True)/1e6
                c["lastmod"] = int.from_bytes(data[144:148], byteorder='little')
                self.contacts[c["adv_name"]]=c
            case 4: # end of contacts
                self.result.set_result(self.contacts)
            case 5: # self info
                self.self_info["adv_type"] = data[1]
                self.self_info["tx_power"] = data[2]
                self.self_info["max_tx_power"] = data[3]
                self.self_info["public_key"] = data[4:36].hex()
                self.self_info["adv_lat"] = int.from_bytes(data[36:40], byteorder='little', signed=True)/1e6
                self.self_info["adv_lon"] = int.from_bytes(data[40:44], byteorder='little', signed=True)/1e6
                #self.self_info["reserved_44:48"] = data[44:48].hex()
                self.self_info["radio_freq"] = int.from_bytes(data[48:52], byteorder='little') / 1000
                self.self_info["radio_bw"] = int.from_bytes(data[52:56], byteorder='little') / 1000
                self.self_info["radio_sf"] = data[56]
                self.self_info["radio_cr"] = data[57]
                self.self_info["name"] = data[58:].decode()
                self.result.set_result(True)
            case 6: # msg sent
                res = {}
                res["type"] = data[1]
                res["expected_ack"] = bytes(data[2:6])
                res["suggested_timeout"] = int.from_bytes(data[6:10], byteorder='little')
                self.result.set_result(res)
            case 7: # contact msg recv
                res = {}
                res["type"] = "PRIV"
                res["pubkey_prefix"] = data[1:7].hex()
                res["path_len"] = data[7]
                res["txt_type"] = data[8]
                res["sender_timestamp"] = int.from_bytes(data[9:13], byteorder='little')
                if data[8] == 2 : # signed packet
                    res["signature"] = data[13:17].hex()
                    res["text"] = data[17:].decode()
                else :
                    res["text"] = data[13:].decode()
                self.result.set_result(res)
            case 16: # a reply to CMD_SYNC_NEXT_MESSAGE (ver >= 3)
                res = {}
                res["type"] = "PRIV"
                res["SNR"] = int.from_bytes(data[1:2], byteorder='little', signed=True) * 4;
                res["pubkey_prefix"] = data[4:10].hex()
                res["path_len"] = data[10]
                res["txt_type"] = data[11]
                res["sender_timestamp"] = int.from_bytes(data[12:16], byteorder='little')
                if data[11] == 2 : # signed packet
                    res["signature"] = data[16:20].hex()
                    res["text"] = data[20:].decode()
                else :
                    res["text"] = data[16:].decode()
                self.result.set_result(res)
            case 8 : # chanel msg recv
                res = {}
                res["type"] = "CHAN"
                res["channel_idx"] = data[1]
                res["path_len"] = data[2]
                res["txt_type"] = data[3]
                res["sender_timestamp"] = int.from_bytes(data[4:8], byteorder='little')
                res["text"] = data[8:].decode()
                self.result.set_result(res)
            case 17: # a reply to CMD_SYNC_NEXT_MESSAGE (ver >= 3)
                res = {}
                res["type"] = "CHAN"
                res["SNR"] = int.from_bytes(data[1:2], byteorder='little', signed=True) * 4;
                res["channel_idx"] = data[4]
                res["path_len"] = data[5]
                res["txt_type"] = data[6]
                res["sender_timestamp"] = int.from_bytes(data[7:11], byteorder='little')
                res["text"] = data[11:].decode()
                self.result.set_result(res)
            case 9: # current time
                self.result.set_result(int.from_bytes(data[1:5], byteorder='little'))
            case 10: # no more msgs
                self.result.set_result(False)
            case 11: # contact
                self.result.set_result("meshcore://" + data[1:].hex())
            case 12: # battery voltage
                self.result.set_result(int.from_bytes(data[1:2], byteorder='little'))
            case 13: # device info
                res = {}
                res["fw ver"] = data[1]
                if data[1] >= 3:
                    res["max_contacts"] = data[2] * 2
                    res["max_channels"] = data[3]
                    res["ble_pin"] = int.from_bytes(data[4:8], byteorder='little')
                    res["fw_build"] = data[8:20].decode().replace("\0","")
                    res["model"] = data[20:60].decode().replace("\0","")
                    res["ver"] = data[60:80].decode().replace("\0","")
                self.result.set_result(res)
            # push notifications
            case 0x80:
                printerr ("Advertisment received")
            case 0x81:
                printerr ("Code path update")
            case 0x82:
                self.ack_ev.set()
                printerr ("Received ACK")
            case 0x83:
                self.rx_sem.release()
                printerr ("Msgs are waiting")
            case 0x84:
                printerr ("Received raw data")
                res = {}
                res["SNR"] = data[1] / 4
                res["RSSI"] = data[2]
                res["payload"] = data[4:].hex()
                print(res)
            case 0x85:
                self.login_resp.set_result(True)

                printerr ("Login success")
            case 0x86:
                self.login_resp.set_result(False)
                printerr ("Login failed")
            case 0x87:
                res = {}
                res["pubkey_pre"] = data[2:8].hex()
                res["bat"] = int.from_bytes(data[8:10], byteorder='little')
                res["tx_queue_len"] = int.from_bytes(data[10:12], byteorder='little')
                res["free_queue_len"] = int.from_bytes(data[12:14], byteorder='little')
                res["last_rssi"] = int.from_bytes(data[14:16], byteorder='little', signed=True)
                res["nb_recv"] = int.from_bytes(data[16:20], byteorder='little', signed=False)
                res["nb_sent"] = int.from_bytes(data[20:24], byteorder='little', signed=False)
                res["airtime"] = int.from_bytes(data[24:28], byteorder='little')
                res["uptime"] = int.from_bytes(data[28:32], byteorder='little')
                res["sent_flood"] = int.from_bytes(data[32:36], byteorder='little')
                res["sent_direct"] = int.from_bytes(data[36:40], byteorder='little')
                res["recv_flood"] = int.from_bytes(data[40:44], byteorder='little')
                res["recv_direct"] = int.from_bytes(data[44:48], byteorder='little')
                res["full_evts"] = int.from_bytes(data[48:50], byteorder='little')
                res["last_snr"] = int.from_bytes(data[50:52], byteorder='little', signed=True) / 4
                res["direct_dups"] = int.from_bytes(data[52:54], byteorder='little')
                res["flood_dups"] = int.from_bytes(data[54:56], byteorder='little')
                self.status_resp.set_result(res)
                data_hex = data[8:].hex()
                printerr (f"Status response: {data_hex}")
                #printerr(res)
            case 0x88:
                printerr ("Received log data")
            # unhandled
            case _:
                printerr (f"Unhandled data received {data}")

    async def send(self, data, timeout = 5):
        """ Helper function to synchronously send (and receive) data to the node """
        self.result = asyncio.Future()
        try:
            await self.cx.send(data)
            res = await asyncio.wait_for(self.result, timeout)
            return res
        except TimeoutError :
            printerr ("Timeout while sending message ...")
            return False

    async def send_only(self, data): # don't wait reply
        await self.cx.send(data)

    async def send_appstart(self):
        """ Send APPSTART to the node """
        b1 = bytearray(b'\x01\x03      mccli')
        return await self.send(b1)

    async def send_device_qeury(self):
        return await self.send(b"\x16\x03");

    async def send_advert(self):
        """ Make the node send an advertisement """
        return await self.send(b"\x07")

    async def set_name(self, name):
        """ Changes the name of the node """
        return await self.send(b'\x08' + name.encode("ascii"))

    async def set_coords(self, lat, lon):
        return await self.send(b'\x0e'\
                + int(lat*1e6).to_bytes(4, 'little', signed=True)\
                + int(lon*1e6).to_bytes(4, 'little', signed=True)\
                + int(0).to_bytes(4, 'little'))

    async def reboot(self):
        await self.send_only(b'\x13reboot')
        return True

    async def get_bat(self):
        return await self.send(b'\x14')

    async def get_time(self):
        """ Get the time (epoch) of the node """
        self.time = await self.send(b"\x05")
        return self.time

    async def set_time(self, val):
        """ Sets a new epoch """
        return await self.send(b"\x06" + int(val).to_bytes(4, 'little'))

    async def set_tx_power(self, val):
        """ Sets tx power """
        return await self.send(b"\x0c" + int(val).to_bytes(4, 'little'))

    async def set_radio (self, freq, bw, sf, cr):
        """ Sets radio params """
        return await self.send(b"\x0b" \
                + int(float(freq)*1000).to_bytes(4, 'little')\
                + int(float(bw)*1000).to_bytes(4, 'little')\
                + int(sf).to_bytes(1, 'little')\
                + int(cr).to_bytes(1, 'little'))

    async def set_tuning (self, rx_dly, af):
        """ Sets radio params """
        return await self.send(b"\x15" \
                + int(rx_dly).to_bytes(4, 'little')\
                + int(af).to_bytes(4, 'little')\
                + int(0).to_bytes(1, 'little')\
                + int(0).to_bytes(1, 'little'))

    async def set_devicepin (self, pin):
        return await self.send(b"\x25" \
                + int(pin).to_bytes(4, 'little'))

    async def get_contacts(self):
        """ Starts retreiving contacts """
        return await self.send(b"\x04")

    async def ensure_contacts(self):
        if len(self.contacts) == 0 :
            await self.get_contacts()

    async def reset_path(self, key):
        data = b"\x0D" + key
        return await self.send(data)

    async def share_contact(self, key):
        data = b"\x10" + key
        return await self.send(data)

    async def export_contact(self, key=b""):
        data = b"\x11" + key
        return await self.send(data)

    async def remove_contact(self, key):
        data = b"\x0f" + key
        return await self.send(data)

    async def set_out_path(self, contact, path):
        contact["out_path"] = path
        contact["out_path_len"] = -1
        contact["out_path_len"] = int(len(path) / 2)

    async def update_contact(self, contact):
        out_path_hex = contact["out_path"]
        out_path_hex = out_path_hex + (128-len(out_path_hex)) * "0" 
        adv_name_hex = contact["adv_name"].encode().hex()
        adv_name_hex = adv_name_hex + (64-len(adv_name_hex)) * "0"
        data = b"\x09" \
            + bytes.fromhex(contact["public_key"])\
            + contact["type"].to_bytes(1)\
            + contact["flags"].to_bytes(1)\
            + contact["out_path_len"].to_bytes(1, 'little', signed=True)\
            + bytes.fromhex(out_path_hex)\
            + bytes.fromhex(adv_name_hex)\
            + contact["last_advert"].to_bytes(4, 'little')\
            + int(contact["adv_lat"]*1e6).to_bytes(4, 'little', signed=True)\
            + int(contact["adv_lon"]*1e6).to_bytes(4, 'little', signed=True)
        return await self.send(data)

    async def send_login(self, dst, pwd):
        self.login_resp = asyncio.Future()
        data = b"\x1a" + dst + pwd.encode("ascii")
        return await self.send(data)

    async def wait_login(self, timeout = 5):
        try :
            return await asyncio.wait_for(self.login_resp, timeout)
        except TimeoutError :
            printerr ("Timeout ...")
            return False

    async def send_statusreq(self, dst):
        self.status_resp = asyncio.Future()
        data = b"\x1b" + dst
        return await self.send(data)

    async def wait_status(self, timeout = 5):
        try :
            return await asyncio.wait_for(self.status_resp, timeout)
        except TimeoutError :
            printerr ("Timeout...")
            return False

    async def send_cmd(self, dst, cmd):
        """ Send a cmd to a node """
        timestamp = (await self.get_time()).to_bytes(4, 'little')
        data = b"\x02\x01\x00" + timestamp + dst + cmd.encode("ascii")
        #self.ack_ev.clear() # no ack ?
        return await self.send(data)

    async def send_msg(self, dst, msg):
        """ Send a message to a node """
        timestamp = (await self.get_time()).to_bytes(4, 'little')
        data = b"\x02\x00\x00" + timestamp + dst + msg.encode("ascii")
        self.ack_ev.clear()
        return await self.send(data)

    async def send_chan_msg(self, chan, msg):
        """ Send a message to a public channel """
        timestamp = (await self.get_time()).to_bytes(4, 'little')
        data = b"\x03\x00" + chan.to_bytes(1, 'little') + timestamp + msg.encode("ascii")
        return await self.send(data)

    async def get_msg(self):
        """ Get message from the node (stored in queue) """
        res = await self.send(b"\x0A", 1)
        if res is False :
            self.rx_sem=asyncio.Semaphore(0) # reset semaphore as there are no msgs in queue
        return res

    async def wait_msg(self, timeout=-1):
        """ Wait for a message """
        if timeout == -1 :
            await self.rx_sem.acquire()
            return True

        try:
            await asyncio.wait_for(self.rx_sem.acquire(), timeout)
            return True
        except TimeoutError :
            printerr("Timeout waiting msg")
            return False

    async def wait_ack(self, timeout=6):
        """ Wait ack """
        try:
            await asyncio.wait_for(self.ack_ev.wait(), timeout)
            return True
        except TimeoutError :
            printerr("Timeout waiting ack")
            return False
