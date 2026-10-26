#!/usr/bin/env python3
"""
ISO 14229 UDS Protocol Implementation
Implements UDS diagnostic services including Security Access, Read Data By Identifier,
and Routine Control for MCM cluster operations.
"""

import logging
from typing import Tuple, Optional, List, Dict
from enum import IntEnum
import time

logger = logging.getLogger(__name__)


class UDSService(IntEnum):
    """UDS Service IDs."""
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    READ_DATA_BY_IDENTIFIER = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    READ_SCALED_ANALOG_IO_DATA = 0x24
    READ_DATA_BY_PERIODIC_DATA_IDENTIFIER = 0x2A
    DYNAMICALLY_DEFINE_DATA_IDENTIFIER = 0x2C
    WRITE_DATA_BY_IDENTIFIER = 0x2E
    INPUT_OUTPUT_CONTROL_BY_IDENTIFIER = 0x2F
    ROUTINE_CONTROL = 0x31
    REQUEST_DOWNLOAD = 0x34
    REQUEST_UPLOAD = 0x35
    TRANSFER_DATA = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    WRITE_MEMORY_BY_ADDRESS = 0x3D
    TESTER_PRESENT = 0x3E
    NEGATIVE_RESPONSE = 0x7F


class UDSSessionType(IntEnum):
    """Diagnostic session types."""
    DEFAULT_SESSION = 0x01
    PROGRAMMING_SESSION = 0x02
    EXTENDED_DIAGNOSTIC_SESSION = 0x03
    SAFETY_SYSTEM_DIAGNOSTIC_SESSION = 0x04


class UDSSecurityLevel(IntEnum):
    """Security access levels."""
    LEVEL_1 = 0x01
    LEVEL_3 = 0x03


class UDSRoutineID(IntEnum):
    """Routine IDs for Routine Control service."""
    TEMPERATURE_CALIBRATION = 0x0101
    MCM_EEPROM_CHECK = 0x0102
    MCM_RAM_TEST = 0x0103


class UDSDataIdentifier(IntEnum):
    """Data Identifiers for Read Data By Identifier."""
    VIN = 0xF190
    CALIBRATION_ID_1 = 0xF191
    CALIBRATION_ID_2 = 0xF192
    ECU_SERIAL_NUMBER = 0xF18C
    HARDWARE_VERSION = 0xF193
    SOFTWARE_VERSION = 0xF194


class UDSNegativeResponseCode(IntEnum):
    """Negative Response Codes."""
    SERVICE_NOT_SUPPORTED = 0x11
    SUB_FUNCTION_NOT_SUPPORTED = 0x12
    INCORRECT_MESSAGE_LENGTH_OR_FORMAT = 0x13
    REQUEST_OUT_OF_RANGE = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    AUTHENTICATION_FAILED = 0x35
    REQUEST_SEQUENCE_ERROR = 0x24
    GENERAL_PROGRAMMING_FAILURE = 0x72


class UDSProtocol:
    """ISO 14229 UDS Protocol handler."""

    def __init__(self, can_transport):
        """
        Initialize UDS protocol.

        Args:
            can_transport: CAN transport layer object with send/receive methods
        """
        self.can_transport = can_transport
        self.current_session = UDSSessionType.DEFAULT_SESSION
        self.security_level = 0
        self.session_timer = time.time()

        logger.info("UDS Protocol initialized")

    def _encode_message(self, service: int, data: bytes = b'') -> bytes:
        """Encode UDS message."""
        return bytes([service]) + data

    def _decode_response(self, response: bytes) -> Tuple[bool, bytes]:
        """
        Decode UDS response.

        Returns:
            Tuple of (is_positive, response_data)
        """
        if len(response) < 1:
            return False, b''

        service_id = response[0]

        if service_id == UDSService.NEGATIVE_RESPONSE:
            if len(response) >= 3:
                neg_service = response[1]
                neg_code = response[2]
                logger.warning(
                    f"Negative response for service 0x{neg_service:02X}: "
                    f"code 0x{neg_code:02X}"
                )
            return False, response[1:]

        return True, response[1:]

    def diagnostic_session_control(
        self,
        session_type: UDSSessionType
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Enter a diagnostic session.

        Args:
            session_type: Session type to enter

        Returns:
            Tuple of (success, response_data)
        """
        logger.info(f"Entering diagnostic session: {session_type}")

        message = self._encode_message(
            UDSService.DIAGNOSTIC_SESSION_CONTROL,
            bytes([session_type])
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                self.current_session = session_type
                self.session_timer = time.time()
                logger.info(f"Successfully entered session {session_type}")
                return True, data

        logger.error(f"Failed to enter session {session_type}")
        return False, None

    def security_access_request_key(
        self,
        security_level: UDSSecurityLevel
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Request security access key (Request Seed).

        Args:
            security_level: Security level to access

        Returns:
            Tuple of (success, seed)
        """
        logger.info(f"Requesting security key for level {security_level}")

        message = self._encode_message(
            UDSService.SECURITY_ACCESS,
            bytes([security_level])
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                logger.info(f"Security seed received: {len(data)} bytes")
                return True, data

        logger.error("Security access request failed")
        return False, None

    def security_access_send_key(
        self,
        security_level: UDSSecurityLevel,
        key: bytes
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Send security access key (Send Key).

        Args:
            security_level: Security level
            key: Calculated security key

        Returns:
            Tuple of (success, response_data)
        """
        logger.info(f"Sending security key for level {security_level}")

        message = self._encode_message(
            UDSService.SECURITY_ACCESS,
            bytes([security_level + 1]) + key  # Odd level is send key
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                self.security_level = security_level
                logger.info("Security access granted")
                return True, data

        logger.error("Security access denied")
        return False, None

    def read_data_by_identifier(
        self,
        identifiers: List[int]
    ) -> Tuple[bool, Dict[int, bytes]]:
        """
        Read data by identifier (VIN, calibration IDs, etc.).

        Args:
            identifiers: List of data identifier IDs

        Returns:
            Tuple of (success, dict of identifier->data)
        """
        logger.info(f"Reading {len(identifiers)} data identifiers")

        # Build identifier list (each is 2 bytes)
        id_bytes = b''.join([identifier.to_bytes(2, byteorder='big') for identifier in identifiers])

        message = self._encode_message(
            UDSService.READ_DATA_BY_IDENTIFIER,
            id_bytes
        )

        success, response = self.can_transport.send_and_receive(message)
        result = {}

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                # Parse response data
                offset = 0
                for identifier in identifiers:
                    # Simplified parsing - in production, handle variable length data
                    if offset < len(data):
                        result[identifier] = data[offset:offset+17]  # VIN is 17 chars
                        offset += 17

                logger.info(f"Successfully read {len(result)} identifiers")
                return True, result

        logger.error("Read data by identifier failed")
        return False, {}

    def routine_control_start(
        self,
        routine_id: int
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Start a routine (e.g., temperature calibration).

        Args:
            routine_id: Routine ID to start

        Returns:
            Tuple of (success, response_data)
        """
        logger.info(f"Starting routine 0x{routine_id:04X}")

        message = self._encode_message(
            UDSService.ROUTINE_CONTROL,
            bytes([0x01]) + routine_id.to_bytes(2, byteorder='big')  # Start
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                logger.info(f"Routine 0x{routine_id:04X} started")
                return True, data

        logger.error(f"Failed to start routine 0x{routine_id:04X}")
        return False, None

    def routine_control_stop(
        self,
        routine_id: int
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Stop a running routine.

        Args:
            routine_id: Routine ID to stop

        Returns:
            Tuple of (success, response_data)
        """
        logger.info(f"Stopping routine 0x{routine_id:04X}")

        message = self._encode_message(
            UDSService.ROUTINE_CONTROL,
            bytes([0x02]) + routine_id.to_bytes(2, byteorder='big')  # Stop
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                logger.info(f"Routine 0x{routine_id:04X} stopped")
                return True, data

        logger.error(f"Failed to stop routine 0x{routine_id:04X}")
        return False, None

    def routine_control_request_results(
        self,
        routine_id: int
    ) -> Tuple[bool, Optional[bytes]]:
        """
        Request routine results.

        Args:
            routine_id: Routine ID

        Returns:
            Tuple of (success, routine_results)
        """
        logger.info(f"Requesting results for routine 0x{routine_id:04X}")

        message = self._encode_message(
            UDSService.ROUTINE_CONTROL,
            bytes([0x03]) + routine_id.to_bytes(2, byteorder='big')  # Request Results
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, data = self._decode_response(response)
            if is_positive:
                logger.info(f"Results received for routine 0x{routine_id:04X}")
                return True, data

        logger.error(f"Failed to get results for routine 0x{routine_id:04X}")
        return False, None

    def tester_present(self, sub_function: int = 0x00) -> Tuple[bool, Optional[bytes]]:
        """
        Send Tester Present to keep session alive.

        Args:
            sub_function: Sub-function (typically 0x00)

        Returns:
            Tuple of (success, response_data)
        """
        message = self._encode_message(
            UDSService.TESTER_PRESENT,
            bytes([sub_function])
        )

        success, response = self.can_transport.send_and_receive(message)

        if success:
            is_positive, _ = self._decode_response(response)
            if is_positive:
                self.session_timer = time.time()
                return True, response

        return False, None

    def is_session_alive(self, timeout_seconds: int = 300) -> bool:
        """Check if session is still alive."""
        return (time.time() - self.session_timer) < timeout_seconds


class CANTransport:
    """CAN transport layer for UDS."""

    def __init__(self, j2534_passthru):
        """
        Initialize CAN transport.

        Args:
            j2534_passthru: J2534PassThru instance
        """
        self.passthru = j2534_passthru
        self.request_id = 0x641
        self.response_id = 0x642
        logger.info("CAN transport initialized")

    def send_and_receive(
        self,
        data: bytes,
        timeout_ms: int = 1000
    ) -> Tuple[bool, bytes]:
        """
        Send UDS message and wait for response.

        Args:
            data: UDS message data
            timeout_ms: Response timeout

        Returns:
            Tuple of (success, response_data)
        """
        # Send request
        can_frame = self.request_id.to_bytes(4, byteorder='big') + data
        success, _ = self.passthru.passthru_write_msg(can_frame, timeout_ms=100)

        if not success:
            logger.error("Failed to send CAN message")
            return False, b''

        # Wait for response
        start_time = time.time()
        while (time.time() - start_time) < (timeout_ms / 1000.0):
            success, messages = self.passthru.passthru_read_msg(timeout_ms=100)

            if success and messages:
                response = messages[0]
                if len(response) > 4:
                    response_data = response[4:]  # Strip CAN ID
                    logger.debug(f"Received response: {response_data.hex()}")
                    return True, response_data

            time.sleep(0.01)

        logger.error("Response timeout")
        return False, b''
