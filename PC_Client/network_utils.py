import socket
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

class SourceAddressAdapter(HTTPAdapter):
    """
    A custom HTTPAdapter that binds outgoing requests to a specific source IP address.
    This is useful for systems with multiple network interfaces (NICs) to ensure
    traffic is routed through the correct interface.
    """
    def __init__(self, source_address, **kwargs):
        """
        :param source_address: The source IP address to bind to (str).
        """
        self.source_address = source_address
        super(SourceAddressAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        # The source_address parameter in PoolManager expects a tuple (ip, port).
        # We specify port 0 to let the OS choose an ephemeral port.
        self._pool_connections = connections
        self._pool_maxsize = maxsize
        self._pool_block = block

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=(self.source_address, 0),
            **pool_kwargs
        )
