import nmap3
import FreeSimpleGUI as sg # use for GUI creation
from pprint import pformat #dict to str

#====Initialize====
nmap_basics = nmap3.Nmap()
nmap_scatec = nmap3.NmapScanTechniques()
nmap_basics_submits = [ #7 Submits
    sg.Text('Basic Nmap functions'),
    sg.Submit("Nmap Version",key="nmap_version"),
    sg.Submit("Scan Top Ports",key="scan_top_ports"),
    sg.Submit("DNS Brute Script",key="dns_brute_script"),
    sg.Submit("List Scan",key="list_scan"),
    sg.Submit("OS Detection",key="os_detection"),
    sg.Submit("Subnet Scan",key="subnet_scan"),
    sg.Submit("Nmap Version Detection",key="nmap_version_detection"),
]
nmap_scatec_submits = [ #6 Submits
    sg.Text('NmapScanTechniques Functions'),
    sg.Submit("FIN Scan",key="fin_scan"),
    sg.Submit("Idle Packet",key="idle_scan"),
    sg.Submit("Ping Scan",key="ping_scan"),
    sg.Submit("SYN Scan",key="syn_scan"),
    sg.Submit("TCP Scan",key="tcp_scan"),
    sg.Submit("UDP Scan",key="udp_scan")
]
sg.theme("LightGreen5")
layout = [
            [sg.Text("[Required]Destination(IPv4): "),sg.InputText("127.0.0.1",key="ipv4_dst")],
            [sg.Text("[Recommended]First: connectivity test by ping scan")],
            nmap_basics_submits,
            nmap_scatec_submits,
            [sg.Text('Statement'),sg.Output(key='statement',size=(50,1)),sg.Cancel("Wanna Cancel",key="cancel")],
            [sg.Text('Results'),sg.Output(key='results',size=(100,15))],
        ]
window = sg.Window(title='python3-nmap GUI for Beginners', layout=layout)

#====Basic Nmap 7 functions====
def nmap_version(): #ping_request
    window['statement'].update("Ready!")
    results = nmap_basics.nmap_version()
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("Completed!")
    window['results'].update(results)

def scan_top_ports(dst):#TCP Port Scan(Well-known)
    window['statement'].update("Ready!")
    results = nmap_basics.scan_top_ports(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("TCP Port Scan Results(SA: open,RA: filtered)")
    window['results'].update(results)

def dns_brute_script(dst):
    window['statement'].update("Ready!")
    results = nmap_basics.nmap_dns_brute_script("domain")
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("DNS_Brute_Script Result")
    window['results'].update(results)

def list_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_basics.nmap_list_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("Nmap List Scan Results")
    window['results'].update(results)

def os_detection(dst): #Must be root
    window['statement'].update("Ready!")
    results = nmap_basics.nmap_os_detection(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("OS Detection Results")
    window['results'].update(results)

def subnet_scan(dst):#Must be root
    window['statement'].update("Ready!")
    results = nmap_basics.subnet_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("Subnet Scan Results")
    window['results'].update(results)

def nmap_version_detection(dst):
    window['statement'].update("Ready!")
    results = nmap_basics.nmap_version_detection(dst)# will add an argument[args="--script vulners --script-args mincvss+5.0"]
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("Nmap Version Detection Results")
    window['results'].update(results)

#====NmapScanTechniques 6 functions=====
def fin_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_fin_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("FIN Scan Result")
    window['results'].update(results)

def idle_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_idle_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("Idle Scan Result")
    window['results'].update(results)

def ping_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_ping_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("ping reply Results")
    window['results'].update(results)

def syn_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_syn_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("SYN Scan Results")
    window['results'].update(results)

def tcp_scan(dst):
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_tcp_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("TCP Scan Results")
    window['results'].update(results)

def udp_scan(dst):#Must be root
    window['statement'].update("Ready!")
    results = nmap_scatec.nmap_udp_scan(dst)
    results = pformat(results,compact=True) #dict to str
    window['statement'].update("UDP Scan Results")
    window['results'].update(results)

#====Operate GUI ====
while True:
    event, values = window.read()
    dst = values["ipv4_dst"]

    #[Execute]: Click "x Button" on upper right, GUI is Closed
    if event == sg.WIN_CLOSED:
        break
    #[Execute]: Click "Wanna Cancel Button", GUI is not Closed but STOP Execute something
    if event == "cancel":
        continue
    #[Execute] Basic Nmap 7 functions
    if event == "nmap_version":
        nmap_version()
    if event == "scan_top_ports":
        scan_top_ports(dst)
    if event == "dns_brute_script":
        dns_brute_script(dst)
    if event == "list_scan":
        list_scan(dst)
    if event == "os_detection":
        os_detection(dst)
    if event == "subnet_scan":
        subnet_scan(dst)
    if event == "nmap_version_detection":
        nmap_version_detection(dst)
    #[Execute] NmapScanTechniques 6 functions=====
    if event == "fin_scan":
        fin_scan(dst)
    if event =="idle_scan":
        idle_scan(dst)
    if event == "ping_scan":
        ping_scan(dst)
    if event == "syn_scan":
        syn_scan(dst)
    if event =="tcp_scan":
        tcp_scan(dst)
    if event == "udp_scan":
        udp_scan(dst)
window.close()

#FreeSimpleGUI Reference: https://github.com/spyoungtech/FreeSimpleGUI
#python3-nmap Reference: https://pypi.org/project/python3-nmap/
#Nmap Reference: https://nmap.org/download.html