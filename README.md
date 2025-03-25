# meshcore-cli

meshcore-cli : CLI interface to MeschCore companion app over BLE, TCP or Serial

## Install

Meshcore-cli depends on the (python meshcore)[https://github.com/fdlamotte/meshcore_py] package. You can install both via `pip` or `pipx` using the command :

 <pre>
$ pipx install meshcore-cli
</pre>

It will install you `meshcore-cli` and `meshcli`, which is an alias to the former.


## Usage

<pre>
$ meshcli &lt;args&gt; &lt;commands&gt;
</pre>

### Arguments

Arguments mostly deals with ble connection

<pre>
    -h : prints this help                                                                      
    -a &lt;address&gt;    : specifies device address (can be a name)
    -d &lt;name&gt;       : filter meshcore devices with name or address
    -t &lt;hostname&gt;   : connects via tcp/ip
    -p &lt;port&gt;       : specifies tcp port (default 5000)
    -s &lt;port&gt;       : use serial port &lt;port&gt;
    -b &lt;baudrate&gt;   : specify baudrate
</pre>

### Available Commands 

Commands are given after arguments, they can be chained and some have shortcuts.

 <pre>
    infos                  : print informations about the node      i 
    reboot                 : reboots node                             
    send &lt;key&gt; &lt;msg&gt;       : sends msg to node using pubkey[0:6]
    sendto &lt;name&gt; &lt;msg&gt;    : sends msg to node with given name        
    msg &lt;name&gt; &lt;msg&gt;       : same as sendto                         m 
    wait_ack               : wait an ack for last sent msg          wa
    recv                   : reads next msg                         r 
    sync_msgs              : gets all unread msgs from the node     sm
    wait_msg               : wait for a message and read it         wm
    advert                 : sends advert                           a 
    contacts               : gets contact list                      lc
    share_contact &lt;ct&gt;     : share a contact with others            sc
    remove_contact &lt;ct&gt;    : removes a contact from this node         
    reset_path &lt;ct&gt;        : resets path to a contact to flood      rp
    change_path &lt;ct&gt; &lt;path&gt;: change the path to a contact           cp
    get_time               : gets current time                        
    set_time &lt;epoch&gt;       : sets time to given epoch                 
    sync_time              : sync time with system                    
    set_name &lt;name&gt;        : sets node name                           
    get_bat                : gets battery level                     b 
    login &lt;name&gt; &lt;pwd&gt;     : log into a node (rep) with given pwd   l 
    wait_login             : wait for login (timeouts after 5sec)   wl
    cmd &lt;name&gt; &lt;cmd&gt;       : sends a command to a repeater (no ack) c 
    req_status &lt;name&gt;      : requests status from a node            rs
    wait_status            : wait and print reply                   ws
    sleep &lt;secs&gt;           : sleeps for a given amount of secs      s
</pre>

### Examples

<pre>
# gets info from first MC device it finds (was -s but now used for serial port)
$ ./mccli.py -d "" infos
Scanning for devices
Found device : F0:F5:BD:4F:9B:AD: MeshCore
Connexion started
{'adv_type': 1, 'public_key': '54c11cff0c2a861cfc5b0bd6e4b81cd5e6ca85e058bf53932d86c87dc7a20011', 'device_loc': '000000000000000000000000', 'radio_freq': 867500, 'radio_bw': 250000, 'radio_sf': 10, 'radio_cr': 5, 'name': 'toto'}
cmd ['infos'] processed ...

$ ./mccli.py -a F0:F5:BD:4F:9B:AD get_time
Connexion started
Current time : 2024-05-15 12:52:53 (1715770373)
cmd ['get_time'] processed ...

$ date
Tue Feb  4 12:55:05 CET 2025

$ ./mccli.py -a F0:F5:BD:4F:9B:AD sync_time get_time
Connexion started
True
cmd ['sync_time'] processed ...
Current time : 2025-02-04 12:55:24 (1738670124)
cmd ['get_time'] processed ...

$ ./mccli.py -a F0:F5:BD:4F:9B:AD contacts
Connexion started
{}
cmd ['contacts'] processed ...

$ ./mccli.py -a F0:F5:BD:4F:9B:AD sleep 10 contacts
Connexion started
Advertisment received
cmd ['sleep', '10'] processed ...
{
    "flo2": {
        "public_key": "d6e43f8e9ef26b801d6f5fee39f55ad6dfabfc939c84987256532d8b94aa25dd",
        "type": 1,
        "flags": 0,
        "out_path_len": 255,
        "out_path": "",
        "adv_name": "flo2",
        "last_advert": 1738670344,
        "adv_lat": 0,
        "adv_lon": 0,
        "lastmod": 1738670354
    }
}
cmd ['contacts'] processed ...

$ ./mccli.py -a F0:F5:BD:4F:9B:AD sendto flo2 "Hello flo2" sleep 10
Connexion started
{'type': 1, 'expected_ack': b'9\x05\x0c\x12', 'suggested_timeout': 3260}
cmd ['sendto', 'flo2', 'Hello flo2'] processed ...
Code path update
Received ACK
Msgs are waiting
cmd ['sleep', '10'] processed ...

$ ./mccli.py -a F0:F5:BD:4F:9B:AD recv
Connexion started
{'type': 'PRIV', 'pubkey_prefix': 'd6e43f8e9ef2', 'path_len': 255, 'txt_type': 0, 'sender_timestamp': 1738670421, 'text': 'hi'}
cmd ['recv'] processed ...

# logs into a repeater (HomeRep) and check time
$ ./mccli.py -d t1000 login HomeRep password
Scanning for devices
Found device : FB:F2:5C:40:4F:77: MeshCore-t1000
Connexion started
{'type': 0, 'expected_ack': b'\x82yU\x02', 'suggested_timeout': 4446}
cmd ['login', 'HomeRep', 'password'] processed ...

$ ./mccli.py cmd HomeRep clock wait_msg
Connexion started
{'type': 0, 'expected_ack': b'\x00\x00\x00\x00', 'suggested_timeout': 2724}
cmd ['cmd', 'HomeRep', 'clock'] processed ...
Msgs are waiting
{'type': 'PRIV', 'pubkey_prefix': '827955027cad', 'path_len': 255, 'txt_type': 1, 'sender_timestamp': 1741030036, 'text': '19:27 - 3/3/2025 UTC'}
cmd ['wait_msg'] processed ...
</pre>

