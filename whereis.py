import socket

def scan_rtsp_network(base_ip="192.168.1.", start=100, end=254, port=554, timeout=2):
    dispositivos = []
    for i in range(start, end+1):
        ip = f"{base_ip}{i}"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            if result == 0:
                print(f"Possível RTSP encontrado em {ip}:{port}")
                dispositivos.append(ip)
            else:
                print(ip, ": nope")    
            sock.close()
        except Exception as e:
            pass
    return dispositivos

# Exemplo de uso
dispositivos_rtsp = scan_rtsp_network()
print("Dispositivos encontrados:", dispositivos_rtsp)
