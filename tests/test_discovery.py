"""
Unit Tests for SHH 1.0 Discovery and Rendezvous
"""

from shh.discovery.ip_detector import IPDetector
from shh.discovery.rendezvous import RendezvousManager
from shh.utils.crypto import pack_connection_ticket, unpack_connection_ticket


def test_ticket_pack_unpack():
    data = {
        "session_id": "shh-test-1234",
        "token": "secret-token-abc",
        "ip": "1.2.3.4",
        "port": 18888
    }
    ticket = pack_connection_ticket(data)
    assert ticket.startswith("shh://")

    unpacked = unpack_connection_ticket(ticket)
    assert unpacked["session_id"] == data["session_id"]
    assert unpacked["token"] == data["token"]
    assert unpacked["port"] == data["port"]


def test_rendezvous_ticket_generation():
    meta = {
        "session_id": "shh-rendezvous-test",
        "token": "test-token",
        "lan_ip": "192.168.1.100",
        "port": 18888
    }
    res = RendezvousManager.publish(meta, provider="none")
    assert res.success is True
    assert res.ticket.startswith("shh://")

    fetched = RendezvousManager.fetch(res.ticket)
    assert fetched["session_id"] == "shh-rendezvous-test"
    assert fetched["token"] == "test-token"


def test_local_ip_detection():
    lan_ip = IPDetector.get_local_lan_ip()
    assert isinstance(lan_ip, str)
    assert len(lan_ip) > 0


if __name__ == "__main__":
    test_ticket_pack_unpack()
    test_rendezvous_ticket_generation()
    test_local_ip_detection()
    print("All discovery tests passed!")
