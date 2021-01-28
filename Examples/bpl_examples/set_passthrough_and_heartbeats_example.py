"""set_passthrough_and_heartbeats_example.py

Sets Passthrough mode and heartbeats on the Bravo Device

Passthrough mode provides the fastest possible communication to Bravo joints. This will disable advanced kinematic
features and protections such as obstacle and collision avoidance.

Heartbeats allow the device to repeatably stream information at a specified frequency. You can select what data
to stream by modifying the HEARTBEAT_PACKETS.

Select your communication method at the bottom of the script, but commenting / uncommenting the relevant function.

DISCLAIMER:
THIS WILL DISABLE SELF COLLISION AND OBSTACLE AVOIDANCE.
USE PASSTHROUGH MODE WITH CAUTION

"""
import re
import socket
import struct
from typing import Union, Tuple, List, Optional
from cobs import cobs
import serial
import time
from crcmod import crcmod
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)

# Device ID of the passthrough board
PASSTHROUGH_BOARD_DEVICE_ID = 0x0D

# Device ID of the Bravo Processor
BRAVO_PROCESSOR_DEVICE_ID = 0x0E

PASSTHROUGH_MODE = 0x06


class PacketID:
    """
    Class holding relevant packet Ids for this script.
    Look in 'from BPL_serial_protocol.RS1_SDK_v4.RS1_SDK.Examples.RS1_hardware' for a comprehensive list of packet ids.
    """

    POSITION = 0x03
    VELOCITY_CONSTRAINT = 0xB5
    REQUEST_PACKET = 0x60
    DEVICE_TYPE = 0x67
    HEARTBEAT_SET = 0x91
    HEARTBEAT_FREQUENCY_SET = 0x92
    SYSTEM_RESET = 0xFD


class BPLProtocol:
    """ Helper class used to encode and decode BPL packets."""

    CRC8_FUNC = crcmod.mkCrcFun(0x14D, initCrc=0xFF, xorOut=0xFF)

    @staticmethod
    def packet_splitter(buff: bytes) -> Tuple[List[bytes], Optional[bytes]]:
        """
        Split packets coming in along bpl protocol, Packets are split via 0x00.
        """
        incomplete_packet = None
        packets = re.split(b'\x00', buff)
        if buff[-1] != b'0x00':
            incomplete_packet = packets.pop()
        return packets, incomplete_packet

    @staticmethod
    def parse_packet(packet_in: Union[bytes, bytearray]) -> Tuple[int, int, bytes]:
        """
        Parse the packet returning a tuple of [int, int, bytes].
         If unable to parse the packet, then return 0,0,b''.
        """

        packet_in = bytearray(packet_in)

        if packet_in and len(packet_in) > 3:
            try:
                decoded_packet: bytes = cobs.decode(packet_in)
            except cobs.DecodeError as e:
                logger.warning(f"parse_packet(): Cobs Decoding Error, {e}")
                return 0, 0, b''

            if decoded_packet[-2] != len(decoded_packet):
                logger.warning(f"parse_packet(): Incorrect length: length is {len(decoded_packet)} "
                               f"in {[hex(x) for x in list(decoded_packet)]}")
                return 0, 0, b''
            else:
                if BPLProtocol.CRC8_FUNC(decoded_packet[:-1]) == decoded_packet[-1]:
                    rx_data = decoded_packet[:-4]

                    device_id = decoded_packet[-3]
                    packet_id = decoded_packet[-4]
                    rx_data = rx_data
                    return device_id, packet_id, rx_data
                else:
                    logger.warning(f"parse_packet(): CRC error in {[hex(x) for x in list(decoded_packet)]} ")
                    return 0, 0, b''
        return 0, 0, b''

    @staticmethod
    def encode_packet(device_id: int, packet_id: int, data: Union[bytes, bytearray]):
        """ Encode the packet using the bpl protocol."""
        tx_packet = bytes(data)
        tx_packet += bytes([packet_id, device_id, len(tx_packet) + 4])
        tx_packet += bytes([BPLProtocol.CRC8_FUNC(tx_packet)])
        packet: bytes = cobs.encode(tx_packet) + b'\x00'
        return packet

    @staticmethod
    def decode_floats(data: Union[bytes, bytearray]) -> List[float]:
        """ Decode a received byte list, into a float list as specified by the bpl protocol"""
        list_data = list(struct.unpack(str(int(len(data) / 4)) + "f", data))
        return list_data

    @staticmethod
    def encode_floats(float_list: List[float]) -> bytes:
        """ Decode a received byte list, into a float list as specified by the bpl protocol"""
        data = struct.pack('%sf' % len(float_list), *float_list)
        return data


def set_passthrough_and_heartbeat_via_serial(device_ids: List[int], heartbeat_packets: List[int], frequency: int):
    """ Setting passthrough via serial."""

    # Create the Serial Connection
    serial_device = serial.Serial(SERIAL_PORT,
                                  baudrate=BAUDRATE,
                                  stopbits=serial.STOPBITS_ONE,
                                  parity=serial.PARITY_NONE,
                                  bytesize=serial.EIGHTBITS)
    serial_device.timeout = 0.01

    # Set the Passthrough board to passthrough mode
    set_passthrough_packet = BPLProtocol.encode_packet(PASSTHROUGH_BOARD_DEVICE_ID,
                                                       PacketID.DEVICE_TYPE,
                                                       bytes([PASSTHROUGH_MODE]))

    serial_device.write(set_passthrough_packet)

    time.sleep(0.2)

    # Reset the Bravo processor
    reset_processor_packet = BPLProtocol.encode_packet(BRAVO_PROCESSOR_DEVICE_ID,
                                                       PacketID.SYSTEM_RESET,
                                                       bytes([0]))
    serial_device.write(reset_processor_packet)

    time.sleep(0.2)

    encoded_velocity_constraints_bytes = BPLProtocol.encode_floats([20.0, -20.0])
    reset_constraints_packet = BPLProtocol.encode_packet(0xFF,
                                                         PacketID.VELOCITY_CONSTRAINT,
                                                         encoded_velocity_constraints_bytes)

    serial_device.write(reset_constraints_packet)

    time.sleep(0.2)

    print("Device is now in passthrough")

    for device_id in device_ids:
        print(f"Setting heartbeat packets for Device {device_id}.")
        set_heart_beat_packet = BPLProtocol.encode_packet(device_id, PacketID.HEARTBEAT_SET, bytes(heartbeat_packets))
        serial_device.write(set_heart_beat_packet)
        time.sleep(0.05)
        set_heartbeat_frequency = BPLProtocol.encode_packet(device_id,
                                                            PacketID.HEARTBEAT_FREQUENCY_SET,
                                                            bytes([frequency]))
        serial_device.write(set_heartbeat_frequency)
        time.sleep(0.05)

    print("Heartbeats are set")



def set_passthrough_and_heartbeat_via_udp(device_ids: List[int], heartbeat_packets: List[int], frequency: int):
    """ Setting passthrough via serial."""

    # Create the udp socket
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setblocking(False)

    # Set the Passthrough board to passthrough mode
    set_passthrough_packet = BPLProtocol.encode_packet(PASSTHROUGH_BOARD_DEVICE_ID,
                                                       PacketID.DEVICE_TYPE,
                                                       bytes([PASSTHROUGH_MODE]))

    udp.sendto(set_passthrough_packet, (UDP_IP_ADDRESS, UDP_PORT))

    time.sleep(0.2)

    # Reset the Bravo processor
    reset_processor_packet = BPLProtocol.encode_packet(BRAVO_PROCESSOR_DEVICE_ID,
                                                       PacketID.SYSTEM_RESET,
                                                       bytes([0]))
    udp.sendto(reset_processor_packet, (UDP_IP_ADDRESS, UDP_PORT))

    time.sleep(0.2)

    encoded_velocity_constraints_bytes = BPLProtocol.encode_floats([20.0, -20.0])
    reset_constraints_packet = BPLProtocol.encode_packet(0xFF,
                                                         PacketID.VELOCITY_CONSTRAINT,
                                                         encoded_velocity_constraints_bytes)

    udp.sendto(reset_constraints_packet, (UDP_IP_ADDRESS, UDP_PORT))

    time.sleep(2.5)

    print("Device is now in passthrough")

    for device_id in device_ids:
        print(f"Setting heartbeat packets for Device {device_id}.")
        set_heart_beat_packet = BPLProtocol.encode_packet(device_id, PacketID.HEARTBEAT_SET, bytes(heartbeat_packets))
        udp.sendto(set_heart_beat_packet, (UDP_IP_ADDRESS, UDP_PORT))
        time.sleep(0.05)
        set_heartbeat_frequency = BPLProtocol.encode_packet(device_id,
                                                            PacketID.HEARTBEAT_FREQUENCY_SET,
                                                            bytearray([frequency]))
        udp.sendto(set_heartbeat_frequency, (UDP_IP_ADDRESS, UDP_PORT))
        time.sleep(0.05)

    print("Heartbeats are set")

SERIAL_PORT = "COM12"  # Serial port in your computer.
BAUDRATE = 115200

UDP_IP_ADDRESS = "192.168.2.3"
UDP_PORT = 6789

HEARTBEAT_PACKETS = [PacketID.POSITION]

HEARTBEAT_FREQUENCY = 0  # HZ

DEVICE_IDS = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]

if __name__ == '__main__':
    i = input(
        "DISCLAIMER: Setting this device into passthrough mode will disable self collision and obstacle avoidance.\n"
        "Are you sure you want to continue? (y/n): ")

    if i == "y":
        print("Setting passthrough")

        """ Uncomment the relevant method you would like the change to apply the passthrough"""
        # set_passthrough_and_heartbeat_via_serial(DEVICE_IDS, HEARTBEAT_PACKETS, HEARTBEAT_FREQUENCY)

        set_passthrough_and_heartbeat_via_udp(DEVICE_IDS, HEARTBEAT_PACKETS, HEARTBEAT_FREQUENCY)

    else:
        print("Ending Script")


