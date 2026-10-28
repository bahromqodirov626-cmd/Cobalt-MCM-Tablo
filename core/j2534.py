#!/usr/bin/env python3
"""
J2534 PassThru API Wrapper
Implements the PassThru (J2534) API using ctypes to load opassthru.dll.
Provides functions for CAN bus communication at 500kbps.
"""

import ctypes
import logging
from ctypes import c_uint32, c_uint8, Structure, c_char_p
from typing import Optional, List, Tuple
from enum import IntEnum

logger = logging.getLogger(__name__)


class PassThruStatus(IntEnum):
    """PassThru status codes."""
    NOERROR = 0x00
    NOT_SUPPORTED = 0x01
    INVALID_CHANNEL_ID = 0x02
    INVALID_PROTOCOL_ID = 0x03
    NULL_PARAMETER = 0x04
    TIMEOUT = 0x05
    MAX_TIMED_OUT = 0x06
    INVALID_IOCTL_ID = 0x07
    INVALID_FLAGS = 0x08
    FAILED = 0x09
    DEVICE_NOT_CONNECTED = 0x0A
    UNABLE_TO_CONNECT = 0x0B
    INVALID_HANDLE = 0x0C
    INVALID_OBJECT_ID = 0x0D
    PENDING = 0x0E
    NO_WRITE_PERMISSION = 0x0F
    DEVICE_IN_USE = 0x10


class ProtocolID(IntEnum):
    """Protocol IDs."""
    J1850VPW = 0x01
    J1850PWM = 0x02
    ISO9141 = 0x03
    ISO14230 = 0x04
    CAN = 0x05
    ISO15765 = 0x06
    SCI_A = 0x07
    SCI_B = 0x08
    ATA = 0x09
    HSFZ = 0x0A


class PassThruMsg(Structure):
    """PassThru message structure."""
    _fields_ = [
        ("ProtocolID", c_uint32),
        ("RxStatus", c_uint32),
        ("TxFlags", c_uint32),
        ("DataSize", c_uint32),
        ("ExtraDataIndex", c_uint32),
        ("Data", c_uint8 * 4096),
    ]


class SConfig(Structure):
    """Configuration structure for PassThru."""
    _fields_ = [
        ("Parameter", c_uint32),
        ("Value", c_uint32),
    ]


class J2534PassThru:
    """J2534 PassThru API wrapper."""

    def __init__(self, dll_path: str = "opassthru.dll"):
        """
        Initialize PassThru wrapper.

        Args:
            dll_path: Path to opassthru.dll
        """
        self.dll_path = dll_path
        self.dll = None
        self.device_id = None
        self.channel_id = None
        self.connect_flags = None

        logger.info(f"Initializing J2534 PassThru from {dll_path}")

    def load_dll(self) -> bool:
        """Load the PassThru DLL."""
        try:
            self.dll = ctypes.WinDLL(self.dll_path)
            logger.info(f"Successfully loaded {self.dll_path}")
            return True
        except OSError as e:
            logger.error(f"Failed to load {self.dll_path}: {e}")
            return False

    def passthru_open(self, name: Optional[str] = None) -> Tuple[bool, Optional[int]]:
        """
        Open PassThru device.

        Args:
            name: Device name (optional)

        Returns:
            Tuple of (success, device_id)
        """
        if not self.dll:
            logger.error("DLL not loaded")
            return False, None

        try:
            device_id = c_uint32()
            name_bytes = name.encode('utf-8') if name else None

            status = self.dll.PassThruOpen(
                c_char_p(name_bytes),
                ctypes.byref(device_id)
            )

            if status == PassThruStatus.NOERROR:
                self.device_id = device_id.value
                logger.info(f"PassThru device opened with ID: {self.device_id}")
                return True, self.device_id
            else:
                logger.error(f"PassThruOpen failed with status: {status}")
                return False, None
        except Exception as e:
            logger.exception(f"PassThruOpen exception: {e}")
            return False, None

    def passthru_connect(
        self,
        protocol_id: ProtocolID = ProtocolID.ISO15765,
        flags: int = 0x00
    ) -> Tuple[bool, Optional[int]]:
        """
        Connect to a protocol channel.

        Args:
            protocol_id: Protocol to connect to
            flags: Connection flags

        Returns:
            Tuple of (success, channel_id)
        """
        if not self.device_id:
            logger.error("Device not opened")
            return False, None

        try:
            channel_id = c_uint32()

            status = self.dll.PassThruConnect(
                c_uint32(self.device_id),
                c_uint32(protocol_id),
                c_uint32(flags),
                c_uint32(500000),  # 500kbps baud rate
                ctypes.byref(channel_id)
            )

            if status == PassThruStatus.NOERROR:
                self.channel_id = channel_id.value
                self.connect_flags = flags
                logger.info(f"Connected to protocol {protocol_id} on channel {self.channel_id}")
                return True, self.channel_id
            else:
                logger.error(f"PassThruConnect failed with status: {status}")
                return False, None
        except Exception as e:
            logger.exception(f"PassThruConnect exception: {e}")
            return False, None

    def passthru_write_msg(self, data: bytes, timeout_ms: int = 100) -> Tuple[bool, int]:
        """
        Write a message to the CAN bus.

        Args:
            data: Message data
            timeout_ms: Timeout in milliseconds

        Returns:
            Tuple of (success, messages_written)
        """
        if not self.channel_id:
            logger.error("Channel not connected")
            return False, 0

        try:
            msg = PassThruMsg()
            msg.ProtocolID = ProtocolID.CAN
            msg.TxFlags = 0x00
            msg.DataSize = len(data)

            for i, byte in enumerate(data):
                msg.Data[i] = byte

            messages_written = c_uint32()

            status = self.dll.PassThruWriteMsg(
                c_uint32(self.channel_id),
                ctypes.byref(msg),
                ctypes.byref(messages_written),
                c_uint32(timeout_ms)
            )

            if status == PassThruStatus.NOERROR:
                logger.debug(f"Wrote {messages_written.value} message(s) to CAN bus")
                return True, messages_written.value
            else:
                logger.error(f"PassThruWriteMsg failed with status: {status}")
                return False, 0
        except Exception as e:
            logger.exception(f"PassThruWriteMsg exception: {e}")
            return False, 0

    def passthru_read_msg(self, timeout_ms: int = 100) -> Tuple[bool, List[bytes]]:
        """
        Read messages from the CAN bus.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Tuple of (success, list_of_messages)
        """
        if not self.channel_id:
            logger.error("Channel not connected")
            return False, []

        try:
            msg = PassThruMsg()
            messages_read = c_uint32()

            status = self.dll.PassThruReadMsg(
                c_uint32(self.channel_id),
                ctypes.byref(msg),
                ctypes.byref(messages_read),
                c_uint32(timeout_ms)
            )

            if status == PassThruStatus.NOERROR:
                message_data = bytes(msg.Data[:msg.DataSize])
                logger.debug(f"Read {messages_read.value} message(s) from CAN bus")
                return True, [message_data]
            else:
                logger.warning(f"PassThruReadMsg status: {status}")
                return False, []
        except Exception as e:
            logger.exception(f"PassThruReadMsg exception: {e}")
            return False, []

    def passthru_close(self) -> bool:
        """
        Close PassThru device.

        Returns:
            Success status
        """
        if not self.device_id:
            logger.warning("Device not opened")
            return False

        try:
            status = self.dll.PassThruClose(c_uint32(self.device_id))

            if status == PassThruStatus.NOERROR:
                logger.info("PassThru device closed")
                self.device_id = None
                self.channel_id = None
                return True
            else:
                logger.error(f"PassThruClose failed with status: {status}")
                return False
        except Exception as e:
            logger.exception(f"PassThruClose exception: {e}")
            return False

    def set_config(self, parameter: int, value: int) -> bool:
        """
        Set PassThru configuration parameter.

        Args:
            parameter: Configuration parameter ID
            value: Parameter value

        Returns:
            Success status
        """
        if not self.channel_id:
            logger.error("Channel not connected")
            return False

        try:
            config = SConfig()
            config.Parameter = parameter
            config.Value = value

            status = self.dll.PassThruSetConfig(
                c_uint32(self.channel_id),
                ctypes.byref(config),
                c_uint32(1)
            )

            if status == PassThruStatus.NOERROR:
                logger.debug(f"Set config parameter {parameter} to {value}")
                return True
            else:
                logger.error(f"PassThruSetConfig failed with status: {status}")
                return False
        except Exception as e:
            logger.exception(f"PassThruSetConfig exception: {e}")
            return False


# Convenience functions for typical CAN bus operations
def create_can_frame(can_id: int, data: bytes) -> bytes:
    """Create a CAN frame with ID and data."""
    frame = can_id.to_bytes(4, byteorder='big') + data
    return frame


def parse_can_frame(frame: bytes) -> Tuple[int, bytes]:
    """Parse a CAN frame into ID and data."""
    can_id = int.from_bytes(frame[:4], byteorder='big')
    data = frame[4:]
    return can_id, data
