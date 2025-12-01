import psutil
import socket
import logging

logger = logging.getLogger(__name__)

class NetworkConfig:
    def __init__(self):
        self.camera_net = None
        self.internet_net = None
        self.all_ifaces = []

    def to_dict(self):
        return {
            "camera_net": self.camera_net,
            "internet_net": self.internet_net,
            "all_ifaces": self.all_ifaces
        }

class NetworkManager:
    def __init__(self):
        self.config = NetworkConfig()

    def detect_interfaces(self):
        """
        Detects all network interfaces and categorizes them into 'camera_net' and 'internet_net'.
        """
        self.config.all_ifaces = []

        # Get network interface stats
        stats = psutil.net_if_stats()
        # Get network interface addresses
        addrs = psutil.net_if_addrs()

        camera_candidate = None
        internet_candidate = None

        for iface_name, iface_addrs in addrs.items():
            # Skip if interface is not up
            if iface_name in stats and not stats[iface_name].isup:
                continue

            # We are interested in IPv4
            ipv4_info = None
            mac_address = None

            for addr in iface_addrs:
                if addr.family == socket.AF_INET:
                    ipv4_info = addr.address
                elif addr.family == psutil.AF_LINK:
                    mac_address = addr.address

            if not ipv4_info or ipv4_info.startswith("127."):
                continue

            iface_details = {
                "name": iface_name,
                "ip": ipv4_info,
                "mac": mac_address
            }
            self.config.all_ifaces.append(iface_details)

            # Categorization Logic
            if ipv4_info.startswith("192.168.4."):
                camera_candidate = iface_details
            elif internet_candidate is None:
                # First valid non-local, non-camera IP is assumed to be internet/LAN
                internet_candidate = iface_details

        self.config.camera_net = camera_candidate
        self.config.internet_net = internet_candidate

        if self.config.camera_net:
            logger.info(f"Camera Net Detected: {self.config.camera_net}")
        else:
            logger.warning("Camera Net (192.168.4.x) NOT Detected.")

        if self.config.internet_net:
            logger.info(f"Internet Net Detected: {self.config.internet_net}")
        else:
            logger.warning("Internet Net NOT Detected.")

        return self.config

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    nm = NetworkManager()
    config = nm.detect_interfaces()
    import json
    print(json.dumps(config.to_dict(), indent=2))
